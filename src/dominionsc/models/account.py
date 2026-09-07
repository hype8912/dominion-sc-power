"""AccountInfo: named replacement for the positional [[types], addr] login result.

The login flow previously built and returned a heterogeneous list::

    accounts = [[]]
    accounts.append(serviceAddressAndAccountNo)   # accounts[1]
    accounts[0].append("ELECTRIC")                # accounts[0]

That structure is annotated list[str] but is actually list[list[str] | str],
read positionally by callers. This dataclass replaces the positional construction
inside LoginFlow while keeping the external contract of async_get_accounts()
unchanged for backward compatibility with ha-dominion-sc.

See docs/REFACTOR_PLAN.md Phase 4 for the breaking-change decision note.
"""

from dataclasses import dataclass, field


@dataclass
class AccountInfo:
    """Named account data returned by the Dominion Energy SC login flow."""

    measurement_types: list[str] = field(default_factory=list)
    """Measurement types active for this account, e.g. ['ELECTRIC', 'GAS']."""

    service_address_and_account_no: str = ""
    """Service address and account number string, e.g. '3005 ELLINGTON DR (*-****-****0-4464)'."""

    def to_legacy_list(self) -> list:
        """Convert to the old positional [[types], addr] format.

        Keeps async_get_accounts() backward-compatible with ha-dominion-sc,
        which destructures the return as::

            accounts, service_addr = await self.api.async_get_accounts()

        where ``accounts`` is a list of measurement-type strings and
        ``service_addr`` is the address/account-number string.
        """
        return [self.measurement_types, self.service_address_and_account_no]
