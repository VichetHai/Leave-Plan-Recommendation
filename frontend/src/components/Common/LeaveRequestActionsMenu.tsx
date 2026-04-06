import { Button, IconButton } from "@chakra-ui/react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { BsThreeDotsVertical } from "react-icons/bs"

import EditLeaveRequest from "../LeaveRequest/EditLeaveRequest"
import { MenuContent, MenuRoot, MenuTrigger } from "../ui/menu"
import { OpenAPI } from "@/client/core/OpenAPI"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"
import type { ApiError } from "@/client/core/ApiError"

interface LeaveTypeInfo {
    id: string
    code: string
    name: string
}

interface OwnerInfo {
    id: string
    full_name: string
    email: string
}

interface ApproverInfo {
    id: string
    full_name: string
    email: string
}

interface LeaveRequestPublic {
    id: string
    start_date: string
    end_date: string
    description: string
    leave_type_id: string
    owner_id: string
    approver_id: string | null
    amount: number
    requested_at: string
    submitted_at: string | null
    approval_at: string | null
    status: string
    owner: OwnerInfo
    leave_type: LeaveTypeInfo
    approver: ApproverInfo | null
}

interface LeaveRequestActionsMenuProps {
    leaveRequest: LeaveRequestPublic
    disabled?: boolean
}

export const LeaveRequestActionsMenu = ({ leaveRequest, disabled }: LeaveRequestActionsMenuProps) => {
    const queryClient = useQueryClient()
    const { showSuccessToast } = useCustomToast()

    // Temporary service calls
    const submitMutation = useMutation({
        mutationFn: async () => {
            const baseUrl = OpenAPI.BASE || ""
            const token = localStorage.getItem("access_token") || ""
            const res = await fetch(`${baseUrl}/api/v1/leave-requests/${leaveRequest.id}/submit`, {
                method: "PUT",
                headers: { Authorization: `Bearer ${token}` },
            })
            if (!res.ok) throw new Error("Failed to submit leave request")
            return res.json()
        },
        onSuccess: () => {
            showSuccessToast("Leave request submitted")
        },
        onError: (err: ApiError) => handleError(err),
        onSettled: () => queryClient.invalidateQueries({ queryKey: ["leave-requests"] }),
    })

    const approveMutation = useMutation({
        mutationFn: async () => {
            const baseUrl = OpenAPI.BASE || ""
            const token = localStorage.getItem("access_token") || ""
            const res = await fetch(`${baseUrl}/api/v1/leave-requests/${leaveRequest.id}/approve`, {
                method: "PUT",
                headers: { Authorization: `Bearer ${token}` },
            })
            if (!res.ok) throw new Error("Failed to approve leave request")
            return res.json()
        },
        onSuccess: () => {
            showSuccessToast("Leave request approved")
        },
        onError: (err: ApiError) => handleError(err),
        onSettled: () => queryClient.invalidateQueries({ queryKey: ["leave-requests"] }),
    })

    const rejectMutation = useMutation({
        mutationFn: async () => {
            const baseUrl = OpenAPI.BASE || ""
            const token = localStorage.getItem("access_token") || ""
            const res = await fetch(`${baseUrl}/api/v1/leave-requests/${leaveRequest.id}/reject`, {
                method: "PUT",
                headers: { Authorization: `Bearer ${token}` },
            })
            if (!res.ok) throw new Error("Failed to reject leave request")
            return res.json()
        },
        onSuccess: () => {
            showSuccessToast("Leave request rejected")
        },
        onError: (err: ApiError) => handleError(err),
        onSettled: () => queryClient.invalidateQueries({ queryKey: ["leave-requests"] }),
    })

    const status = leaveRequest.status
    const isDraft = status === "draft"
    const isPending = status === "pending"


    return (
        <MenuRoot>
            <MenuTrigger asChild>
                <IconButton variant="ghost" color="inherit" disabled={disabled}>
                    <BsThreeDotsVertical />
                </IconButton>
            </MenuTrigger>
            <MenuContent>
                {/* Draft: Edit, Submit */}
                {isDraft && (
                    <>
                        <EditLeaveRequest leaveRequest={leaveRequest} />
                        <Button variant="ghost" size="sm" onClick={() => submitMutation.mutate()} disabled={submitMutation.isPending}>
                            Submit
                        </Button>
                    </>
                )}
                {/* Pending: Approve, Reject only */}
                {isPending && (
                    <>
                        <Button variant="ghost" size="sm" onClick={() => approveMutation.mutate()} disabled={approveMutation.isPending}>
                            Approve
                        </Button>
                        <Button variant="ghost" size="sm" colorPalette="red" onClick={() => rejectMutation.mutate()} disabled={rejectMutation.isPending}>
                            Reject
                        </Button>
                    </>
                )}
            </MenuContent>
        </MenuRoot>
    )
}
