"""MCP server exposing tools over an Order entity.

Everything under "Domain layer" has no dependency on FastMCP or the mcp
package and can be imported/tested standalone. Everything under "MCP layer"
is a thin adapter that exposes that layer as tools.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypedDict

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("order_server")

ORDERS_FILE = Path("/Users/irinaason/Java/AI/AI_DD/proshop_mern/admin-api/orders.json")

Status = Literal["new", "paid", "delivered"]
PaymentMethod = Literal["PayPal", "Stripe"]


class OrderState(TypedDict):
    order_id: str
    status: Status
    isPaid: bool
    isDelivered: bool
    paymentMethod: PaymentMethod | None
    updatedAt: str


class OrderTransitionState(OrderState):
    previous_status: Status


# ===========================================================================
# Domain layer -- no MCP/FastMCP dependency. Importable and testable standalone.
# ===========================================================================


class OrderError(Exception):
    """Raised when a requested change violates an order invariant."""


def compute_status(is_paid: bool, is_delivered: bool) -> Status:
    if is_paid and is_delivered:
        return "delivered"
    if is_paid:
        return "paid"
    return "new"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class OrderStore:
    """In-memory order table backed by a JSON file.

    Stores only the raw fields (isPaid/isDelivered/paymentMethod/updatedAt);
    `status` is always derived via compute_status, never stored.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._orders: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        with self._path.open("r", encoding="utf-8") as f:
            self._orders = json.load(f)
        logger.info("loaded %d orders from %s", len(self._orders), self._path)

    def _save(self) -> None:
        with self._path.open("w", encoding="utf-8") as f:
            json.dump(self._orders, f, indent=2)
            f.write("\n")

    def _get_raw(self, order_id: str) -> dict:
        order = self._orders.get(order_id)
        if order is None:
            raise OrderError(f"unknown order_id: {order_id!r}")
        return order

    @staticmethod
    def _state(order_id: str, order: dict) -> OrderState:
        return {
            "order_id": order_id,
            "status": compute_status(order["isPaid"], order["isDelivered"]),
            "isPaid": order["isPaid"],
            "isDelivered": order["isDelivered"],
            "paymentMethod": order["paymentMethod"],
            "updatedAt": order["updatedAt"],
        }

    def get_state(self, order_id: str) -> OrderState:
        self._load()
        order = self._get_raw(order_id)
        return self._state(order_id, order)

    def change_status(
        self, order_id: str, target_status: Literal["paid", "delivered"]
    ) -> OrderTransitionState:
        self._load()
        order = self._get_raw(order_id)
        current = compute_status(order["isPaid"], order["isDelivered"])

        if current == "delivered":
            raise OrderError("cannot change status: order is delivered (terminal status)")

        if target_status == "paid":
            if current != "new":
                raise OrderError(f"cannot transition to paid from {current}")
            if not order["paymentMethod"]:
                raise OrderError("cannot transition to paid: paymentMethod is not set")
            order["isPaid"] = True

        elif target_status == "delivered":
            if current == "new":
                raise OrderError("cannot skip paid: order must be paid before it can be delivered")
            order["isDelivered"] = True

        order["updatedAt"] = _now_iso()
        self._save()

        new_state = self._state(order_id, order)
        return {**new_state, "previous_status": current}

    def set_payment_method(
        self, order_id: str, payment_method: PaymentMethod | None
    ) -> OrderState:
        self._load()
        order = self._get_raw(order_id)
        current = compute_status(order["isPaid"], order["isDelivered"])

        if current != "new":
            raise OrderError(f"cannot change paymentMethod after payment (status={current})")

        order["paymentMethod"] = payment_method
        order["updatedAt"] = _now_iso()
        self._save()

        return self._state(order_id, order)


# ===========================================================================
# MCP layer -- thin adapter. All logic lives above.
# ===========================================================================

from mcp.server.fastmcp import FastMCP  # noqa: E402

mcp = FastMCP("order-server", host="0.0.0.0", port=8001)
store = OrderStore(ORDERS_FILE)


@mcp.tool()
def get_order_state(order_id: str) -> OrderState:
    """Returns the full current state of an order: its computed status, raw flags, payment method, and last-updated timestamp. `order_id` identifies which order to look up.

    When to call: any time you need to know an order's current status or paymentMethod before deciding whether a transition or a payment-method change is allowed -- including right before calling `change_order_status` or `set_payment_method` if you're unsure of the current state.

    When NOT to call: don't call this to *change* anything -- it is read-only and has no side effects.

    Returns:
    {
      order_id: str,
      status: "new" | "paid" | "delivered",
      isPaid: bool,
      isDelivered: bool,
      paymentMethod: "PayPal" | "Stripe" | null,
      updatedAt: str (ISO 8601)
    }

    Examples:
    - get_order_state(order_id="ord_1") -> {"order_id": "ord_1", "status": "new", "isPaid": false, "isDelivered": false, "paymentMethod": null, "updatedAt": "2026-08-20T10:00:00Z"}
    - get_order_state(order_id="ord_2") -> {"order_id": "ord_2", "status": "paid", "isPaid": true, "isDelivered": false, "paymentMethod": "Stripe", "updatedAt": "2026-08-22T14:30:00Z"}
    """
    return store.get_state(order_id)


@mcp.tool()
def change_order_status(
    order_id: str, target_status: Literal["paid", "delivered"]
) -> OrderTransitionState:
    """Changes an order's status by advancing it along the allowed path new -> paid -> delivered. `order_id` identifies the order; `target_status` ("paid" or "delivered") is the status to move it to. Enforces all transition invariants: blocks `paid` until `paymentMethod` is set, blocks skipping `paid` to go straight to `delivered`, and blocks any transition once an order is `delivered`. On success, updates `updatedAt`.

    When to call: to advance an order after confirming (via `get_order_state` if needed) that the current status and `paymentMethod` make the target transition valid.

    When NOT to call: don't call this to set `paymentMethod` -- use `set_payment_method` first if it's missing. Don't call this on an order already `delivered`.

    Returns: the order's full state after the attempted change, plus `previous_status` showing what it was before this call.
    {
      order_id: str,
      status: "new" | "paid" | "delivered",
      isPaid: bool,
      isDelivered: bool,
      paymentMethod: "PayPal" | "Stripe" | null,
      updatedAt: str (ISO 8601),
      previous_status: "new" | "paid" | "delivered"
    }
    On a forbidden transition, returns an error describing which invariant blocked it instead of changing state.

    Examples:
    - Allowed: change_order_status(order_id="ord_1", target_status="paid") when status is "new" and paymentMethod="PayPal" -> {"order_id": "ord_1", "status": "paid", "isPaid": true, "isDelivered": false, "paymentMethod": "PayPal", "updatedAt": "2026-08-25T09:00:00Z", "previous_status": "new"}
    - Forbidden: change_order_status(order_id="ord_1", target_status="delivered") when status is "new" -> error: "cannot skip paid: order must be paid before it can be delivered".

    Constraint: You MUST NOT call this with target_status="paid" without first confirming paymentMethod is set (via get_order_state), and you MUST NOT attempt any transition when the order's current status is "delivered" -- it is terminal.
    """
    return store.change_status(order_id, target_status)


@mcp.tool()
def set_payment_method(
    order_id: str, payment_method: PaymentMethod | None
) -> OrderState:
    """Sets or clears an order's `paymentMethod`. `order_id` identifies the order; pass `"PayPal"` or `"Stripe"` as `payment_method` to set it, or `null` to clear it. Only permitted while the order's status is `new`; updates `updatedAt` on success.

    When to call: before transitioning an order to `paid` (to set the method), or to correct/clear a payment method on an order that hasn't been paid yet.

    When NOT to call: don't call this on an order whose status is `paid` or `delivered` -- the method is locked in once payment has happened, in either direction (set or clear).

    Returns: the order's full state after the attempted change.
    {
      order_id: str,
      status: "new" | "paid" | "delivered",
      isPaid: bool,
      isDelivered: bool,
      paymentMethod: "PayPal" | "Stripe" | null,
      updatedAt: str (ISO 8601)
    }
    On a forbidden call (status != new), returns an error instead of changing state.

    Examples:
    - Allowed: set_payment_method(order_id="ord_1", payment_method="Stripe") when status is "new" -> {"order_id": "ord_1", "status": "new", "isPaid": false, "isDelivered": false, "paymentMethod": "Stripe", "updatedAt": "2026-08-25T09:05:00Z"}
    - Forbidden: set_payment_method(order_id="ord_2", payment_method=null) when status is "paid" -> error: "cannot change paymentMethod after payment (status=paid)".

    Constraint: You MUST NOT call this (to set or clear paymentMethod) on an order whose status is not "new" -- check get_order_state first if unsure.
    """
    return store.set_payment_method(order_id, payment_method)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")