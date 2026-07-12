import ast
import pandas as pd
from sklearn.ensemble import RandomForestRegressor

from typing import Any
from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, SessionDep
from app.models import LeaveRecommendations
from app.models import User
from app.leave_models.leave_policy_model import Policy
from app.leave_models.public_holiday_model import PublicHoliday
from app.leave_models.leave_plan_request_model import LeavePlanDetail, LeavePlanRequest
from app.leave_models.leave_type_model import LeaveType
from app.leave_models.leave_balance_model import LeaveBalance
from sqlmodel import select, func
from datetime import datetime


class RecommendLeavePlanRouter:
    def __init__(self):
        self.router = APIRouter(
            prefix="/recommends",
            tags=["recommends"]
        )
        
        self.router.add_api_route(
            "/leave-plan",
            self.recommend_leave_plan,
            methods=["GET"],
            response_model=LeaveRecommendations,
        )

    # ---------------------------
    # Endpoint
    # ---------------------------
    def recommend_leave_plan(
        self,
        session: SessionDep,
        current_user: CurrentUser,
        year: int = Query(default=datetime.now().year, description="Year to generate leave recommendations")
    ) -> Any:
        """
        Retrieve items.
        """
        self.year = year
        self.current_user = current_user
        leave_type_id, leave_entitlement = self.get_leave_type_with_balance(session=session)
        data = self.generate_leave_data(session=session)
        _, data = self.train_leave_model(data)
        recommendations = self.recommend_leave_days(data, leave_entitlement=leave_entitlement)
        response_list = self.format_recommendations_for_response(recommendations)
        
        return LeaveRecommendations(
            data=response_list, 
            leave_type_id=leave_type_id, 
            year=self.year
        )
    
    # ---------------------------
    # Helper methods
    # ---------------------------

    def get_leave_type_with_balance(self, session):
        statement = select(LeaveType).where((LeaveType.is_active == True) & (LeaveType.is_allow_plan == True))
        leave_type = session.exec(statement).first()

        if not leave_type:
            raise HTTPException(status_code=404, detail="No leave type found that is allowed for leave planning.")
        
        # Query LeaveBalance 
        balance_statement = select(LeaveBalance).where(
            (LeaveBalance.leave_type_id == leave_type.id) &
            (LeaveBalance.owner_id == self.current_user.id) &
            (LeaveBalance.year == str(self.year))
        )
        leave_balance = session.exec(balance_statement).first()
        available_balance = leave_balance.available_balance if leave_balance else 0
        
        if available_balance == 0:
            raise HTTPException(status_code=404, detail="No remaining leave balance available to create a leave plan.")
        
        return leave_type.id, available_balance

    def format_recommendations_for_response(self, recommendations):
        """
        Convert a DataFrame of recommended leave days to a list of dicts
        matching the Pydantic response model.
        """

        # Select only relevant columns
        response_df = recommendations[["date", "bridge_holiday", "team_workload", "preference_score", "predicted_score"]]

        # Rename columns to match Pydantic model
        response_df = response_df.rename(columns={"date": "leave_date"})

        # Convert to list of dicts for Pydantic
        response_list = response_df.to_dict(orient="records")
        return response_list
    
    def get_holidays(self, data, session):
        # public_holidays = ["2025-01-01", "2025-01-14", "2025-01-07"]
        statement = select(PublicHoliday.date).where(PublicHoliday.date.like(f"{self.year}-%"))
        results = session.exec(statement)
        public_holidays = results.all()

        holidays = pd.to_datetime(public_holidays)
        data["is_holiday"] = data["date"].isin(holidays) | data["weekday"].isin([5,6])
        return data

    def find_bridge_days(self, data):
        data = data.sort_values("date").reset_index(drop=True)
        bridge_day = []
        for i in range(len(data)):
            if data.loc[i, "is_holiday"]:
                bridge_day.append(False)
            elif (i > 0 and data.loc[i-1, "is_holiday"]) and (i < len(data)-1 and data.loc[i+1, "is_holiday"]):
                bridge_day.append(True)
            else:
                bridge_day.append(False)
        data["bridge_holiday"] = bridge_day
        return data

    def set_total_team(self, session):
        statement = select(func.count()).select_from(User).where(User.team_id == self.current_user.team_id)
        self.total_team = session.exec(statement).one()
    
    def get_team_workloads(self, data, session):
        self.set_total_team(session)
        statement = select(
            LeavePlanDetail.leave_date,
            func.count(LeavePlanDetail.id).label("total_leave_days")
        ).join(
            LeavePlanRequest,
            LeavePlanDetail.leave_plan_id == LeavePlanRequest.id
        ).where(
            (LeavePlanRequest.team_id == self.current_user.team_id) &
            (LeavePlanRequest.year == str(self.year))  # filter by year
        ).group_by(
            LeavePlanDetail.leave_date
        ).order_by(
            LeavePlanDetail.leave_date
        )
        results = session.exec(statement).all()

        team_workload_dict = {
            date_obj.strftime("%Y-%m-%d"): count
            for date_obj, count in results
        }
        team_workload_dict = {pd.to_datetime(k): v for k, v in team_workload_dict.items()}
        data["team_workload"] = data["date"].map(team_workload_dict).fillna(data["team_workload"])
        return data

    def set_recommend_policy(self, data, session):
        # dynamic policies
        # policies = [    
        #     {"code": "weekday", "operation": "in", "value": "[0,4]", "score": 1},
        #     {"code": "bridge_holiday", "operation": "==", "value": "True", "score": 2},
        #     {"code": "team_workload", "operation": ">", "value": "50%", "score": -2},
        # ]
        statement = select(Policy).where(Policy.is_active==True)
        policies = session.exec(statement).all()

        # Initialize score column
        data["preference_score"] = 0

        # Apply each policy dynamically
        for p in policies:
            col = p.code
            op = p.operation
            val = p.value
            score = int(p.score)

            # Convert value string safely
            try:
                if col == "team_workload" and val.endswith("%"):
                    val = self.total_team * float(val.strip("%")) / 100
                val = ast.literal_eval(val)
            except (ValueError, SyntaxError):
                pass  # leave as string or number        

            # Apply condition dynamically
            if op == "in":
                if isinstance(val, list):
                    mask = data[col].isin(val)
                else:
                    mask = data[col] == val
            elif op == ">":
                mask = data[col] > float(val)
            elif op == "<":
                mask = data[col] < float(val)
            elif op == ">=":
                mask = data[col] >= float(val)
            elif op == "<=":
                mask = data[col] <= float(val)
            elif op == "==":
                mask = data[col] == val
            else:
                continue  # unknown operation, skip

            # Add or subtract score
            data.loc[mask, "preference_score"] += score
        return data

    def generate_leave_data(self, session):
        days = pd.date_range(f"{self.year}-01-01", periods=365)
        data = pd.DataFrame({
            "day_of_year": days.dayofyear,
            "date": days,
            "weekday": days.weekday,
            "team_workload": 0,
        })
        data = self.get_holidays(data=data, session=session)
        data = self.find_bridge_days(data)
        data = self.get_team_workloads(data=data, session=session)
        data = self.set_recommend_policy(data=data, session=session)
        return data

    def train_leave_model(self, data):
        X = data[["day_of_year", "team_workload"]]
        y = data["preference_score"]
        model = RandomForestRegressor(n_estimators=50, random_state=42)
        model.fit(X, y)
        data["predicted_score"] = model.predict(X)
        return model, data

    def recommend_leave_days(self, data, leave_entitlement=18):
        selected_days = []
        sorted_data = data.sort_values("predicted_score", ascending=False)
        for _, row in sorted_data.iterrows():
            selected_days.append(row.day_of_year)
            if len(selected_days) == leave_entitlement:
                break
        recommendations = data[data.day_of_year.isin(selected_days)].sort_values("day_of_year")
        return recommendations

router = RecommendLeavePlanRouter().router