import unittest

from app import domain_rules
from app.domain import cap, contracts, exceptions, trade_rules
from app import server


class DomainModuleBoundaryTests(unittest.TestCase):
    def test_compatibility_facade_reexports_authoritative_rules(self) -> None:
        self.assertIs(domain_rules.cap_hold_amount, cap.cap_hold_amount)
        self.assertIs(
            domain_rules.minimum_contract_team_salary,
            contracts.minimum_contract_team_salary,
        )
        self.assertIs(domain_rules.format_trade_money, trade_rules.format_trade_money)
        self.assertIs(
            domain_rules.offseason_exception_amounts,
            exceptions.offseason_exception_amounts,
        )

    def test_server_uses_extracted_exception_rules(self) -> None:
        self.assertIs(server.offseason_exception_amounts, exceptions.offseason_exception_amounts)
        self.assertIs(server.offseason_exception_item, exceptions.offseason_exception_item)
        self.assertIs(
            server.OFFSEASON_EXCEPTION_DEFINITIONS,
            exceptions.OFFSEASON_EXCEPTION_DEFINITIONS,
        )

    def test_exception_amounts_scale_from_salary_cap(self) -> None:
        amounts = exceptions.offseason_exception_amounts(165_000_000)

        self.assertEqual(6_064_000, amounts["tmle"])
        self.assertEqual(round(165_000_000 * 0.0912), round(amounts["ntmle"]))

    def test_trade_and_contract_modules_are_directly_usable(self) -> None:
        self.assertEqual("post30", trade_rules.normalize_trade_bucket("post-30"))
        self.assertEqual("$1.250.000", trade_rules.format_trade_money(1_250_000))
        self.assertEqual(
            2_296_274,
            contracts.minimum_salary_for_season(154_647_000, 2, 1),
        )


if __name__ == "__main__":
    unittest.main()
