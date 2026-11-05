"""Household application service: thin facade over the store."""

from __future__ import annotations

from argus.domain.household.schemas import (
    AccountGrantRecord,
    CreateAccountGrantRequest,
    CreateHouseholdRequest,
    HouseholdRecord,
    InvitationCreated,
    Permission,
    SharedAccountView,
    UpdateAccountGrantRequest,
)


class HouseholdService:
    def __init__(self, repository, invite_settings=None) -> None:  # noqa: ANN001
        from argus.domain.household.invite_codes import InviteSettings

        self._repository = repository
        self._invite_settings = invite_settings or InviteSettings.from_env()

    def create(self, *, user_id: str, request: CreateHouseholdRequest) -> HouseholdRecord:
        return self._repository.create_household(
            user_id=user_id, name=request.name, display_name=request.display_name
        )

    def list(self, *, user_id: str) -> list[HouseholdRecord]:
        return self._repository.list_households(user_id=user_id)

    def get(self, *, user_id: str, household_id: str) -> HouseholdRecord:
        return self._repository.get_household(user_id=user_id, household_id=household_id)

    def invite(self, *, user_id: str, household_id: str) -> InvitationCreated:
        from argus.domain.household.invite_codes import invite_link

        created = self._repository.create_invitation(
            user_id=user_id, household_id=household_id
        )
        if created.token is None:
            return created
        return created.model_copy(
            update={
                "link": invite_link(
                    created.token, household=True, settings=self._invite_settings
                )
            }
        )

    def revoke_invitation(
        self, *, user_id: str, household_id: str, invitation_id: str
    ) -> None:
        self._repository.revoke_invitation(
            user_id=user_id, household_id=household_id, invitation_id=invitation_id
        )

    def accept(
        self,
        *,
        user_id: str,
        token: str | None = None,
        display_name: str = "Member",
        code: str | None = None,
    ):
        return self._repository.accept_invitation(
            user_id=user_id, token=token, display_name=display_name, code=code
        )

    def leave(self, *, user_id: str, household_id: str) -> None:
        self._repository.leave(user_id=user_id, household_id=household_id)

    def remove_member(
        self, *, user_id: str, household_id: str, member_user_id: str
    ) -> None:
        self._repository.remove_member(
            admin_user_id=user_id,
            household_id=household_id,
            member_user_id=member_user_id,
        )

    def transfer_admin(
        self, *, user_id: str, household_id: str, new_admin_user_id: str
    ) -> HouseholdRecord:
        return self._repository.transfer_admin(
            admin_user_id=user_id,
            household_id=household_id,
            new_admin_user_id=new_admin_user_id,
        )

    def close(self, *, user_id: str, household_id: str) -> HouseholdRecord:
        return self._repository.close(user_id=user_id, household_id=household_id)

    def create_grant(
        self,
        *,
        user_id: str,
        household_id: str,
        request: CreateAccountGrantRequest,
    ) -> AccountGrantRecord:
        return self._repository.create_grant(
            user_id=user_id,
            household_id=household_id,
            account_id=request.account_id,
            permission=request.permission,
            recipient_membership_id=request.recipient_membership_id,
        )

    def update_grant(
        self,
        *,
        user_id: str,
        household_id: str,
        grant_id: str,
        request: UpdateAccountGrantRequest,
    ) -> AccountGrantRecord:
        return self._repository.update_grant(
            user_id=user_id,
            household_id=household_id,
            grant_id=grant_id,
            permission=request.permission,
        )

    def revoke_grant(self, *, user_id: str, household_id: str, grant_id: str) -> None:
        self._repository.revoke_grant(
            user_id=user_id, household_id=household_id, grant_id=grant_id
        )

    def list_shared_accounts(
        self, *, user_id: str, household_id: str
    ) -> list[SharedAccountView]:
        return self._repository.list_shared_accounts(
            user_id=user_id, household_id=household_id
        )

    def permission_for(
        self, *, user_id: str, household_id: str, account_id: str
    ) -> Permission | None:
        for item in self.list_shared_accounts(user_id=user_id, household_id=household_id):
            if item.account_id == account_id:
                return item.permission
        return None

    def execute(self, *, actor, operation, key, body, household_id, action):
        if hasattr(self._repository, "connection"):
            from .commands import execute

            return execute(
                self._repository,
                actor=actor,
                operation=operation,
                key=key,
                body=body,
                household_id=household_id,
                action=action,
            )
        return self._repository.execute(
            actor=actor,
            operation=operation,
            key=key,
            body=body,
            household_id=household_id,
            action=action,
        )

    def preview_invitation(self, *, user_id, token=None, code=None):
        return self._repository.preview_invitation(
            user_id=user_id, token=token, code=code
        )

    def replace_grants(self, *, user_id, household_id, account_id, recipients):
        return self._repository.replace_grants(
            user_id=user_id,
            household_id=household_id,
            account_id=account_id,
            recipients=recipients,
        )

    @property
    def clock(self):
        return self._repository._clock

    def transaction(self, actor, household_id):
        from contextlib import contextmanager

        @contextmanager
        def transaction():
            with self._repository.connection() as c, c.transaction():
                h = self._repository._require_member_row(
                    c, user_id=actor, household_id=household_id
                )
                yield c, h, {"id": h["membership_id"]}

        return transaction()
