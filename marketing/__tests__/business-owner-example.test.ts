import { describe, test } from "bun:test";
import { deepEqual, equal } from "node:assert/strict";
import { accountSummary, budgetActual, exampleBudgets, exampleGoal, exampleMovements, movementCashEffect, projectedCash } from "../components/owner-example";

describe("Business illustrative money", () => {
  test("keeps currencies separate and derives balances from movements", () => {
    deepEqual(accountSummary("DOP"), { opening: 62000, change: 17700, cash: 79700, income: 18000, expenses: 8900 });
    deepEqual(accountSummary("USD"), { opening: 900, change: 0, cash: 900, income: 0, expenses: 0 });
  });
  test("a personally paid business expense does not reduce business cash", () => {
    const expense = exampleMovements.find((movement) => movement.account === "personal")!;
    equal(expense.kind, "expense");
    equal(expense.amount, 1600);
    equal(movementCashEffect(expense), 0);
    equal(accountSummary("DOP").expenses, 8900);
  });
  test("owner money changes cash without becoming sales or operating expenses", () => {
    const ownerMoney = exampleMovements.filter((movement) => movement.kind === "owner-contribution" || movement.kind === "owner-withdrawal");
    deepEqual(ownerMoney.map(movementCashEffect), [10000, -3000]);
    equal(accountSummary("DOP").income, 18000);
    equal(accountSummary("DOP").expenses, 8900);
  });
  test("budgets report recorded expenses and reserves do not spend cash", () => {
    const cashBefore = accountSummary("DOP").cash;
    deepEqual(exampleBudgets.map((budget) => budgetActual(budget.movementIds)), [2800, 4500, 1600]);
    equal(exampleGoal.saved / exampleGoal.target, 0.5);
    equal(accountSummary("DOP").cash, cashBefore);
  });
  test("a delayed collection changes only the projection, not actual balances", () => {
    const before = accountSummary("DOP");
    equal(projectedCash(false), 71200);
    equal(projectedCash(true), 41200);
    equal(projectedCash(true) - projectedCash(false), -30000);
    deepEqual(accountSummary("DOP"), before);
  });
});
