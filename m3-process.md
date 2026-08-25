# Лог процесса: модуль 3

Трек: normal

## Этап 1. Подготовка данных и контракт инструментов

**Задача:** Нужно спроектировать контракт из 3-х MCP тулов для Order: 
* чтение состояния
* смена статуса с проверкой инвариантов
* изменение paymentMethod. 

Надо получить не код, а набор схем и описаний, который агент сможет использовать без подсказок.

**План:** 
* Заполнила карту проекта для себя (она не закомичена), чтобы увидеть более полную картину
* Заполнила секцию инварианты
* Составила промпт для IDE-агента с чётким списком трёх функций

**Промпты:** 

Промпт 1
```
I'm building an MCP server (Python 3.10+, FastMCP + Pydantic) over an Order entity.

Entity model:
- Raw fields: _id, isPaid (bool), isDelivered (bool), paymentMethod (string, unset or "PayPal"/"Stripe"), updatedAt
- Computed status: new / paid / delivered (derived from isPaid + isDelivered, not a raw field)
- Dependency field: paymentMethod — required before transitioning to "paid"; can only be set or cleared while status is "new"

Repo state:
- m3-report.md is committed and has the "Инварианты сущности" section already filled in — read it first, don't redefine invariants
- project-map.md exists locally (gitignored, not committed) as my own planning notes — you can read it for context but it's not part of the deliverable

Task: design the TOOLS CONTRACT only — no server code yet, that's the next step.

The tool set must cover exactly three user-facing functions, split into 2–3 tools total:
1. Read state — returns the current state of the entity, including the paymentMethod dependency.
2. Change state — changes status with invariant checks (e.g. blocks the transition to "paid" until paymentMethod is set).
3. Set payment method — sets or clears paymentMethod, with a check that clearing it is only allowed while status is "new" (so it never leaves the order in an invalid state). This tool also updates the timestamp.

For each tool, propose:
1. Tool name and which of the three functions above it closes
2. What the schema enforces (e.g. paymentMethod as a Literal["PayPal", "Stripe"], not a bare string) vs. what the code enforces (the transition invariants)
3. A full description draft with three required parts: what it does, when to call it, when NOT to call it — plus a "Returns:" block describing the output shape, and 1–3 realistic call examples (for the state-changing tools, include one example of an allowed transition and one of a forbidden one)
4. One explicit imperative constraint sentence (e.g. "You MUST NOT transition to 'paid' while paymentMethod is unset") for any tool with irreversible or constrained behavior

Show me the proposed contract first and wait for my approval before editing any file. Once I confirm, fill it into the "## Контракт инструментов" table (and description drafts below it) in m3-report.md, replacing the TODOs there — don't touch other sections, and don't write mcp/order_server.py yet.
```

Промпт 2
```
Please revise the proposed tools contract with these fixes:

1. change_order_status's description doesn't mention updating updatedAt in prose. It's in the Returns block, but not stated explicitly like set_payment_method ("updates updatedAt on success"). Add an equivalent sentence for consistency, since both tools mutate state.

2. Parameters aren't explained inline in the description text, only in the table. set_payment_method does this well ("Pass 'PayPal' or 'Stripe' to set it, or null to clear it"), but change_order_status and get_order_state don't spell out what target_status/order_id mean or how they affect behavior directly in the prose — add that.

3. Unify the response shape across all three tools instead of each returning a different payload. All three should return the full order state (same shape as get_order_state's Returns), plus an optional field for operation-specific detail on top — don't drop the useful detail, just make the base consistent:

{
  order_id: str,
  status: "new" | "paid" | "delivered",
  isPaid: bool,
  isDelivered: bool,
  paymentMethod: "PayPal" | "Stripe" | null,
  updatedAt: str (ISO 8601),
  previous_status?: "new" | "paid" | "delivered"  // only present on change_order_status
}

get_order_state and set_payment_method drop the previous_status field entirely (never include it, not even as null). Update each tool's Returns block and examples to match this shared shape.

Show me the revised contract first and wait for my approval before editing m3-report.md.
```


**Что пошло не так:** первая версия не проговаривала параметры и updatedAt в прозе (только в таблице), плюс три инструмента возвращали разные формы payload — пришлось попросить агента унифицировать.


**Итог:** контракт потребовал 2 захода (первичная генерация + один раунд правок).

## TODO: Этап 2. Реализация сервера

<те же пять пунктов>

## TODO: Этап 3. Подключение к хосту и прогон сценария

<те же пять пунктов>