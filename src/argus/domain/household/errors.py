"""Domain failures for the household permission surface."""

from __future__ import annotations


class HouseholdError(Exception):
    code: str
    detail: str

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.detail
        super().__init__(self.detail)


class HouseholdNotFound(HouseholdError):
    code = "household_not_found"
    detail = "No such household."


class HouseholdClosed(HouseholdError):
    code = "household_closed"
    detail = "This household is closed."


class NotAMember(HouseholdError):
    code = "not_a_member"
    detail = "You are not an active member of this household."


class AdminRequired(HouseholdError):
    code = "household_admin_required"
    detail = "Only the household administrator can do that."


class MustTransferOrClose(HouseholdError):
    code = "must_transfer_or_close"
    detail = "Transfer administration or close the household before leaving."


class MemberNotFound(HouseholdError):
    code = "household_member_not_found"
    detail = "No such active household member."


class InvitationNotFound(HouseholdError):
    code = "invitation_not_found"
    detail = "No such invitation."


class InvitationExpired(HouseholdError):
    code = "invitation_expired"
    detail = "This invitation has expired."


class InvitationRevoked(HouseholdError):
    code = "invitation_revoked"
    detail = "This invitation was revoked."


class InvitationConsumed(HouseholdError):
    code = "invitation_consumed"
    detail = "This invitation was already used."


class AccountNotOwned(HouseholdError):
    code = "account_not_owned"
    detail = "You can only share an account you own."


class GrantNotFound(HouseholdError):
    code = "account_grant_not_found"
    detail = "No such account grant."


class HouseholdRule(HouseholdError):
    def __init__(self, code: str):
        self.code = code
        self.detail = "The household changed. Refresh and try again."
        super().__init__()


class BetaQuotaExhausted(HouseholdError):
    code = "beta_invite_quota_exhausted"
    detail = "You have used all of your beta invites."


class FounderRequired(HouseholdError):
    code = "founder_required"
    detail = "Only the founder can do that."


class BetaInviteRequired(HouseholdError):
    code = "beta_invite_required"
    detail = "An invite code is required to use Cuadrao."


class GroupLinkFull(HouseholdError):
    code = "group_link_full"
    detail = "This invite link is full. You are on the waitlist."


class HouseholdInvitationKind(HouseholdError):
    code = "household_invitation_requires_accept"
    detail = "This is a household invitation. Accept it from Household."


class InviteRuleViolation(HouseholdError):
    code = "invite_request_invalid"
    detail = "The invite request is not valid."


class VerifiedUserRequired(HouseholdError):
    code = "verified_user_required"
    detail = "Sign in to use invites."


class InviteCodesUnavailable(HouseholdError):
    code = "invite_codes_unavailable"
    detail = "Invite codes are not configured on this server."
