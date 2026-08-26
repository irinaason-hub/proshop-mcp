# Отчёт по домашке модуля 3: свой MCP-сервер

Трек: normal

Ключевая сущность: Order, proshop_mern, backend/models/orderModel.js

Стек: 
- Python 3.10+
- MCP SDK: `mcp>=1.27,<2` (линия v1 — обязательна верхняя граница, иначе PyPI поставит v2 с несовместимым API)
- Менеджер окружения: venv + pip

Хост: Claude Desktop

## Инварианты сущности

| Переход | Разрешён | Условие |
|---|---|---|
| new → paid	| да	| paymentMethod заполнен |
| new → delivered |	нет |	нельзя пропускать paid|
| paid → delivered |	да |	— |
| paid → new |	нет |	оплату нельзя отменить |
| delivered → любой |	нет |	терминальный статус |

Дополнительное поле: 
* paymentMethod  - можно изменить, только пока status == new. После оплаты (paid/delivered) менять способ оплаты нельзя.

## Контракт инструментов

| Инструмент | Что закрывает | Что проверяет схема | Что проверяет код |
|---|---|---|---|
| `get_order_state` | Функция 1: чтение состояния | `order_id`: обязательная непустая строка | Вычисляет `status` из `isPaid`+`isDelivered` (false/false→new, true/false→paid, true/true→delivered); читает `paymentMethod`, `updatedAt` как есть |
| `change_order_status` | Функция 2: смена статуса | `order_id`: строка; `target_status`: `Literal["paid","delivered"]` (enum — `"new"` недостижим как цель перехода) | Все переходы из таблицы инвариантов: `new→paid` только если `paymentMethod` задан; `new→delivered` запрещён (нельзя пропускать paid); `paid→delivered` разрешён; `paid→new` запрещён; `delivered→*` запрещён (терминальный статус) |
| `set_payment_method` | Функция 3: установка/снятие paymentMethod | `order_id`: строка; `payment_method`: `Literal["PayPal","Stripe"] \| None` (произвольная строка схемой запрещена) | Любое изменение (установка ИЛИ снятие в null) разрешено только при текущем `status == "new"`; иначе отказ; при успехе обновляет `updatedAt` |

### 1. `get_order_state`

**Description:**
> Returns the full current state of an order: its computed status, raw flags, payment method, and last-updated timestamp. `order_id` identifies which order to look up.
>
> When to call: any time you need to know an order's current status or paymentMethod before deciding whether a transition or a payment-method change is allowed — including right before calling `change_order_status` or `set_payment_method` if you're unsure of the current state.
>
> When NOT to call: don't call this to *change* anything — it is read-only and has no side effects.
>
> Returns:
> ```
> {
>   order_id: str,
>   status: "new" | "paid" | "delivered",
>   isPaid: bool,
>   isDelivered: bool,
>   paymentMethod: "PayPal" | "Stripe" | null,
>   updatedAt: str (ISO 8601)
> }
> ```

**Examples:**
- `get_order_state(order_id="ord_1")` → `{order_id: "ord_1", status: "new", isPaid: false, isDelivered: false, paymentMethod: null, updatedAt: "2026-08-20T10:00:00Z"}`
- `get_order_state(order_id="ord_2")` → `{order_id: "ord_2", status: "paid", isPaid: true, isDelivered: false, paymentMethod: "Stripe", updatedAt: "2026-08-22T14:30:00Z"}`

Нет императивного ограничения — только чтение, необратимых эффектов нет.

### 2. `change_order_status`

**Description:**
> Changes an order's status by advancing it along the allowed path new → paid → delivered. `order_id` identifies the order; `target_status` ("paid" or "delivered") is the status to move it to. Enforces all transition invariants: blocks `paid` until `paymentMethod` is set, blocks skipping `paid` to go straight to `delivered`, and blocks any transition once an order is `delivered`. On success, updates `updatedAt`.
>
> When to call: to advance an order after confirming (via `get_order_state` if needed) that the current status and `paymentMethod` make the target transition valid.
>
> When NOT to call: don't call this to set `paymentMethod` — use `set_payment_method` first if it's missing. Don't call this on an order already `delivered`.
>
> Returns: the order's full state after the attempted change, plus `previous_status` showing what it was before this call.
> ```
> {
>   order_id: str,
>   status: "new" | "paid" | "delivered",
>   isPaid: bool,
>   isDelivered: bool,
>   paymentMethod: "PayPal" | "Stripe" | null,
>   updatedAt: str (ISO 8601),
>   previous_status: "new" | "paid" | "delivered"
> }
> ```
> On a forbidden transition, returns an error describing which invariant blocked it instead of changing state.

**Examples:**
- Allowed: `change_order_status(order_id="ord_1", target_status="paid")` when status is `new` and `paymentMethod="PayPal"` → `{order_id: "ord_1", status: "paid", isPaid: true, isDelivered: false, paymentMethod: "PayPal", updatedAt: "2026-08-25T09:00:00Z", previous_status: "new"}`
- Forbidden: `change_order_status(order_id="ord_1", target_status="delivered")` when status is `new` → error: "cannot skip paid".

**Constraint:** You MUST NOT call `change_order_status` with `target_status="paid"` without first confirming `paymentMethod` is set (via `get_order_state`), and you MUST NOT attempt any transition when the order's current status is `delivered` — it is terminal.

### 3. `set_payment_method`

**Description:**
> Sets or clears an order's `paymentMethod`. `order_id` identifies the order; pass `"PayPal"` or `"Stripe"` as `payment_method` to set it, or `null` to clear it. Only permitted while the order's status is `new`; updates `updatedAt` on success.
>
> When to call: before transitioning an order to `paid` (to set the method), or to correct/clear a payment method on an order that hasn't been paid yet.
>
> When NOT to call: don't call this on an order whose status is `paid` or `delivered` — the method is locked in once payment has happened, in either direction (set or clear).
>
> Returns: the order's full state after the attempted change.
> ```
> {
>   order_id: str,
>   status: "new" | "paid" | "delivered",
>   isPaid: bool,
>   isDelivered: bool,
>   paymentMethod: "PayPal" | "Stripe" | null,
>   updatedAt: str (ISO 8601)
> }
> ```
> On a forbidden call (status != new), returns an error instead of changing state.

**Examples:**
- Allowed: `set_payment_method(order_id="ord_1", payment_method="Stripe")` when status is `new` → `{order_id: "ord_1", status: "new", isPaid: false, isDelivered: false, paymentMethod: "Stripe", updatedAt: "2026-08-25T09:05:00Z"}`
- Forbidden: `set_payment_method(order_id="ord_2", payment_method=null)` when status is `paid` → error: "cannot change paymentMethod after payment".

**Constraint:** You MUST NOT call `set_payment_method` (to set or clear) on an order whose status is not `new` — check `get_order_state` first if unsure.

## TODO: Скриншот

![Список инструментов в Inspector](<путь к файлу>)

## TODO: Прогон 1: тестовый сценарий

**Промпт:**
<полный текст>

**Цепочка вызовов** (имена инструментов, аргументы, ответы):
<лог целиком; длинный убирайте под спойлер, но не обрезайте>

**Собралась ли цепочка с первого раза:** <да / нет; если нет, что пошло не так
и какие формулировки в описаниях это вызвали>

## TODO: Прогон 2: запрещённый переход

**Промпт:**
<полный текст>

**Что вернул сервер:**
<текст отказа дословно>

**Что сделала модель после отказа:** <исправилась сама / попросила помощи / зациклилась>

<!-- дальше только advanced -->

## TODO: Прогон 3: токен (advanced)

**Чужой токен:** <получить токен через prepare_* для одного объекта, вызвать с ним
confirm_* для другого; вызовы и ответ сервера>

**Повторный confirm с тем же токеном:** <вызовы и ответ сервера>

## TODO: Прогон 4: prepare не меняет состояние (advanced)

**Три вызова подряд** (чтение, prepare_*, чтение):
<лог целиком, включая отметку времени в обоих чтениях>

## TODO: Переезд в четвёртый и шестой модули

<Какие функции вашего кода переживут переезды без правок, какие придётся менять
и почему, что бы вы сделали иначе, зная про оба переезда заранее. С именами
ваших функций, а не общими словами.>