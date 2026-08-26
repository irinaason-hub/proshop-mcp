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

## Этап 2. Реализация сервера

**Задача:** Написать mcp/order_server.py — MCP-сервер с чётким разделением между доменным слоем (класс OrderStore: валидация переходов, проверка paymentMethod, обновление updatedAt) и тонким MCP-слоем (три @mcp.tool() функции), в точности соответствующий уже утверждённому контракту инструментов из m3-report.md. Плюс тестовые данные orders.json.

**План:** Сначала определила стек(venv+pip, mcp>=1.27,<2, pydantic>=2), чтобы версия SDK не расползалась. Агенту явно указала читать уже согласованный контракт из m3-report.md вместо того, чтобы переизобретать имена инструментов, схемы и описания заново. Критерий разделения слоёв сформулировала как проверяемое условие ("если снять декораторы, код должен остаться рабочим"), а не общей фразой. После того как агент предложил структуру файлов и её приняла — отдельным промптом, без изменения кода, попросили агента отчитаться по четырём конкретным рискам, которые контракт явно не проговаривает: слияние order_id при чтении (JSON хранит id только как ключ словаря), изоляция формы ответа от формы хранения, поведение same-status перехода (не описано в таблице инвариантов), содержательность текстов ошибок. Отдельный ревью-промпт выбрала специально — чтобы не полагаться на "агент сам скажет, если что-то не так", а проверить точечно то, что не покрыто ни схемой, ни контрактом.

**Промпты:** 

Промпт 1
```
I'm building an MCP server (Python 3.10+, FastMCP) over an Order entity. Stack decisions:
- Environment: venv + pip
- Manifest: pyproject.toml, with mcp pinned as mcp>=1.27,<2 (must stay on v1 — v2 renamed FastMCP to MCPServer and moved the import path)
- pydantic>=2 for schemas

Entity model:
- Raw fields: _id, isPaid (bool), isDelivered (bool), paymentMethod (unset or "PayPal"/"Stripe"), updatedAt
- Computed status: new / paid / delivered (derived from isPaid + isDelivered)
- paymentMethod is settable/clearable only while status is "new"

The tools contract is already approved and written in m3-report.md, under "## Контракт инструментов" — read it first and use those tool names, schemas, descriptions, Returns blocks, and examples verbatim. Don't redesign or rephrase them.

Task: write the actual server as a single file, mcp/order_server.py.

Hard requirement: business logic must be separable from the MCP wrapping. Concretely — if I mentally (or actually) strip out the FastMCP import and all @mcp.tool() decorators, the remaining code must still work standalone: the transition validation, the paymentMethod rules, and the updatedAt refresh must live in plain functions or a class that the tool functions merely call. The @mcp.tool()-decorated functions should be a thin layer only — no validation logic inside them directly.

Data source: mcp/orders.json — a small manually-written file with 3–4 orders using the raw fields above (_id, isPaid, isDelivered, paymentMethod, updatedAt). Leave paymentMethod unset on at least one order so there's something for set_payment_method to act on. Create this file if it doesn't exist yet.

Other requirements:
- All debug/log output goes to stderr only — stdout is reserved for the protocol.
- Schema constraints belong in the schema, not just in code: paymentMethod as Literal["PayPal", "Stripe"] | None, target_status as Literal["paid", "delivered"].
- Every mutating tool updates updatedAt on success.
- Also create pyproject.toml with the pinned dependencies above.

Show me the file structure and a summary of what you're about to write before creating the files, and wait for my go-ahead.
```

Промпт 2
```
Please review the current mcp/order_server.py against these points and report back — only fix something if you find an actual problem, don't rewrite anything that's already correct.

1. order_id merging: Confirm that get_state, change_status, and set_payment_method in OrderStore all merge the order_id (the dict key from orders.json) into their returned dict, since the JSON file stores id only as the key, not as a field inside each order object. Show me the relevant lines for each of the three methods.

2. Persistence isolation: Confirm that whatever gets written back to orders.json when saving state does NOT include order_id as a duplicate field inside the object — it should only ever exist as the dict key. If the same dict that's returned to the caller (which has order_id merged in) is also the dict being persisted, that's a bug — the "return shape" and the "storage shape" must not be the same object.

3. Same-status transition: What currently happens if change_order_status is called with target_status equal to the order's current status (e.g. target_status="paid" when the order is already paid)? Show me the exact behavior. This case isn't explicitly covered in the invariants table, so tell me how it's currently handled and let me decide if that's the right call.

4. Error message content: Show me the exact text of the OrderError message for each of the three forbidden transitions (new→delivered, paid→new, and any transition out of delivered) plus the forbidden set_payment_method case. Each message should name which invariant blocked the transition and, where applicable, what to do instead — not a generic message like "invalid transition". Quote the actual strings from the code.

Report findings for all four points before making any changes.
```

**Что пошло не так:** По факту ни первый прогон (создание файла), ни ревью-промпт не выявили ошибок в коде — все четыре проверяемых пункта подтвердились как реализованные корректно с первого раза. Единственное найденное — не баг, а асимметрия: сообщения об ошибке для same-status переходов отличаются по специфичности (`paid→paid` называет конкретный статус, `delivered→delivered` — общая формулировка про терминальность). Решила не чинить сразу, а перепроверить на живом прогоне 2 (запрещённый переход), достаточно ли текущая формулировка понятна модели, вместо того чтобы переписывать четыре сообщения вслепую.

**Итог:** 2 захода — создание файлов + один ревью-проход без правок кода. В следующий раз стоит сразу включать в первый промпт требование к содержанию текстов ошибок (называть конкретный инструмент, который нужно вызвать сначала, как в эталонном примере задания), а не откладывать эту проверку на потом.

## TODO: Этап 3. Подключение к хосту и прогон сценария

<те же пять пунктов>