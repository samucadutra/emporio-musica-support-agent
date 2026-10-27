# Data inventory

Read-only inspection of `data/`, done on 2026-10-27, which is the "today" used throughout this document.
The figures come from `scripts/inspect_data.py` (`uv run python scripts/inspect_data.py`).
Nothing in `data/` was modified.

## 1. Files overview

| File | Size | Rows | Encoding | Delimiter | Decimals | Line endings |
|---|---|---|---|---|---|---|
| `desafio_tecnico_ai_eng - categories.csv` | 756 B | 9 | UTF-8, no BOM | `,` | n/a | CRLF, no final newline |
| `desafio_tecnico_ai_eng - customers.csv` | 3.7 KB | 50 | UTF-8, no BOM | `,` | n/a | CRLF, no final newline |
| `desafio_tecnico_ai_eng - products.csv` | 22 KB | 65 | UTF-8, no BOM | `,` | `1234.56` (dot, no `R$`, no thousands separator) | CRLF, no final newline |
| `desafio_tecnico_ai_eng - promotions.csv` | 839 B | 25 | UTF-8, no BOM | `,` | integers | CRLF, no final newline |
| `desafio_tecnico_ai_eng - orders.csv` | 1.3 KB | 20 | UTF-8, no BOM | `,` | `1234.56` | CRLF, no final newline |
| `desafio_tecnico_ai_eng - order_items.csv` | 230 B | 22 | ASCII | `,` | integers | CRLF, no final newline |
| `políticas_da_loja.pdf` | 176 KB | 8 pages | text PDF (Google Docs/Skia) | n/a | `R$ 1.234,56` in prose | n/a |

Notes:
- The file names carry a `desafio_tecnico_ai_eng - ` prefix with spaces (a Google Sheets export). The loader should map logical table names to these files.
- Each file has a `*:Zone.Identifier` sibling of 25 bytes. These are Windows "downloaded from the internet" metadata copied over by WSL. **Ignore them** (exclude them by glob).
- Text fields with commas are correctly quoted. The `specs` column holds JSON with doubled quotes (`""`), and the standard CSV parser handles it.
- Every date is ISO `YYYY-MM-DD`. No mixed date formats were found.

## 2. Per-table details

### categories (PK `category_id`)
- Columns: `category_id` int, `name` str, `description` str. No nulls and no duplicates.
- Values: 1 Guitarras, 2 Baixos, 3 Baterias e Percussão, 4 Teclados e Pianos, 5 Violões, 6 Instrumentos de Sopro (Madeiras), 7 Instrumentos de Sopro (Metais), 8 Cordas Orquestrais, 9 Ukuleles.
- **Categories 6, 7 and 8 have no products.**

### customers (PK `customer_id`)
- Columns: `customer_id` int (1–50, contiguous), `name`, `phone`, `email`, `city`. No nulls or empty strings, and no leading/trailing whitespace.
- Sample: `1, Lucas Mendes da Silva, (67) 99812-3456, lucas.mendes@jmail.com, Campo Grande`
- Every phone matches `(67) 9XXXX-XXXX`, and every email is well formed. The email domains are fictional: jmail.com 21, coldmail.com 10, inlook.com 10, hayoo.com.br 9.
- `city` values: Campo Grande 24, Dourados 7, Três Lagoas 7, Corumbá 6, Ponta Porã 6.
- **IDs 11 ("Bruno Carvalho Martins") and 43 ("Bruno Martins") share the email `bruno.martins@jmail.com`.**
- Records 1–18 have full names with accents, and every one of them has at least one order. Records 19–50 look generated: two-word names, some missing accents ("Joao Silva", "Leticia Gomes", "Julia Carvalho"), and none have orders.
- Similar names with different emails: 13 "Diego Fernandes Castro" (`diego.castro@coldmail.com`) and 47 "Diego Castro" (`diego.castro@jmail.com`).

### products (PK `product_id`)
- Columns: `product_id` int, `price_brl` float, `name`, `category_id` int, `description`, `stock_quantity` int, `status`, `specs` (JSON string), `created_at` (ISO date).
- No nulls, no duplicates (either full rows or by ID) and no duplicate names.
- IDs run 81–145, but **145 sits between 130 and 131** in the file, so the file isn't sorted.
- Sample:
  - `81, 599.9, Yamaha C40 Nylon Natural, 5, …, 12, active`
  - `95, 2199, Takamine GD20 Dreadnought Natural, 5, …, 5, active`
  - `145, 12500, Fender Stratocaster American Pro II, 1, …, 5, active`
- Products per category: Violões 35, Ukuleles 15, Guitarras 5, Baixos 4, Baterias 3, Teclados 3.
- `status`: `active` 62, `discontinued` 2 (113, 136), `coming_soon` 1 (130).
- Prices range from R$159.90 to R$19,567.00, with none ≤ 0. Stock is never negative. Stock is 0 for **96 (active)** and 113 (discontinued). Product **136 is discontinued but has 13 in stock.**
- `created_at` runs from 2020-02-28 to 2025-05-15.
- Every `specs` value parses as JSON. The key sets differ by category:
  - Violões and Ukuleles: `top, back_sides, neck, strings, scale, electronics, color`
  - Guitarras and Baixos: `body, neck, strings, color`
  - Baterias: `shells, pieces, hardware, color`
  - Teclados: `keys, type, polyphony, color`
- IDs 135–144 use a different JSON spacing (`"key": "value"`). They were added later and look synthetic. See the data-quality section below.

### promotions (PK `promotion_id`)
- Columns: `promotion_id` int, `product_id` int, `discount_percent` int (5–40), `description` str (the campaign name), `is_active` 0/1.
- **There are no start or end dates.** `is_active` is the only signal: 21 rows are 0 and 4 are 1.
- Active promotions:

| promotion_id | product | discount | campaign | list → promo price |
|---|---|---|---|---|
| 12 | 127 Kalani KAL-700T Tenor Natural | 10% | Oferta Especial | 359.00 → 323.10 |
| 14 | 121 Ohana CK-20 Concert Natural | 20% | Desconto Exclusivo | 549.00 → 439.20 |
| 19 | 90 Crafter HT-100 Folk Aço Natural | 18% | Desconto Exclusivo | 2399.00 → 1967.18 |
| 24 | 94 Taylor 110e Dreadnought Natural | 8% | Desconto Exclusivo | 5999.00 → 5519.08 |

- Campaign names: Aniversário da Loja 4, then 3 each of Black Friday, Liquidação de Inverno, Queima de Estoque, Oferta Especial, Promoção de Páscoa, Semana do Músico and Desconto Exclusivo.
- Products 93, 96 and 99 each have two promotions, all inactive. No product has more than one active promotion.

### orders (PK `order_id`)
- Columns: `order_id` int (1–20), `customer_id` int, `order_date`, `status`, `total_brl` float, `payment_method`, `tracking_code`, `estimated_delivery`, `notes`.
- Sample: `1, 3, 2025-10-15, delivered, 11499, pix, BRAB1234567BR, 2025-10-25,`
- `status`: delivered 7, confirmed 4, pending 4, cancelled 4, shipped 1. No invalid values.
- `payment_method`: pix 5, credit_12x 4, credit_6x 3, credit_3x 3, boleto 3, debit 2.
- Empty strings: `tracking_code` and `estimated_delivery` are empty in 12 rows, exactly the confirmed, pending and cancelled ones. `notes` is empty in 16 rows; only the cancelled orders have notes, giving the cancellation reason.
- `order_date` runs from 2025-10-15 to 2026-03-22, and `estimated_delivery` from 2025-10-25 to 2026-02-28.
- Every tracking code matches the policy format `BR` + 9 alphanumeric characters + `BR`.
- **There is no actual delivery or receipt date.** Only `estimated_delivery` exists.

### order_items (no PK; composite `(order_id, product_id)` is unique)
- Columns: `order_id` int, `quantity` int, `product_id` int. 22 rows; orders 15 and 20 have two items each.
- Only order 3 has a quantity above 1 (2×).

## 3. Relationships

```
categories 1─* products 1─* promotions
                 │
                 └─* order_items *─1 orders *─1 customers
```

| FK | Orphans |
|---|---|
| `products.category_id → categories` | none |
| `promotions.product_id → products` | none |
| `order_items.order_id → orders` | none; every order has at least one item |
| `order_items.product_id → products` | none |
| `orders.customer_id → customers` | none |

Referential integrity is clean. Customer 3 has orders 1 and 19, and customer 7 has orders 2 and 20.

## 4. Data quality issues

Severity reflects impact on the agent: **High** means the agent could state something wrong, **Medium** means an edge case to handle, **Low** is cosmetic.

| # | Issue | Severity | Proposed cleaning / handling rule (in code, never in `data/`) |
|---|---|---|---|
| 1 | No actual delivery date. The return window (§4.1) and the legal warranty (§8.1) count from **receipt**. | High | Treat `estimated_delivery` as the receipt date for `delivered` orders, and say so in the README. For `shipped` orders the receipt date is unknown, so the window hasn't started. |
| 2 | Today (2026-10-27) every order is 219–377 days old, so **none is inside any return or warranty window**, and order 8 is "shipped" with an estimated delivery 8 months ago. | High | Make the reference date configurable (e.g. `STORE_TODAY` in settings, defaulting to the real date) so that demos and tests are deterministic. See decision D1 in the Resolved decisions section. |
| 3 | Promotions have no dates, only `is_active`. | High | A promotion is current only when `is_active == 1` **and** the product is `active` with stock > 0 (policy §6.2: promotions depend on stock). Assert at most one current promotion per product. |
| 4 | Products 135–144 contradict themselves: the brand in the name doesn't match the description. 135 "Music Man Bass 1X" is described as a Fender Jazz Bass. 136 "Ibanez Bass 2X" is described as a Precision bass. 137 "Yamaha" is described as an Ibanez with 5 strings, but its specs say `strings: 4`. 139 "Yamaha" is described as a Pearl Export, and 140 "Pearl" as a Tama. 142 "Korg" is described as a Roland with 88 keys, but its specs say 61. 144 "Roland" is described as a Yamaha arranger. Their names are generic ("Kit 1", "Synth 2 Pro") and their prices odd (8732, 11445, 19567). | High | Use `name`, `price_brl`, `stock_quantity` and `status` as the source of truth. Mark these IDs `description_reliable = False` and never quote their description or specs to customers; give only the name and price. Confirmed in decision D4. |
| 5 | Order 3: `total_brl` 3450 ≠ 2 × 1749 = 3498. Order 20: 1400 ≠ 799 + 689 = 1488. | Medium | `total_brl` is the amount actually charged and is reported as-is. Never recompute an order total from current prices, and never present a current price as the price paid. |
| 6 | Orders 3 (delivered) and 14 contain product 130, which is `coming_soon`. | Medium | Treat order data as historical and don't validate it against current status. For catalogue answers, show `coming_soon` as "em breve", not available to buy. |
| 7 | PIX orders (1, 5, 10, 13, 17) were charged the full list price, although the policy gives 5% off with PIX. | Low | Only for the price quoted to customers: compute the PIX price as `price × 0.95` when there's no active promotion. Don't "fix" historical totals. |
| 8 | Installment minimums are violated: order 9 is 6× R$58.32 (minimum R$80), order 16 is 6× R$71.65 (minimum R$80) and order 18 is 12× R$38.32 (minimum R$100). | Low | Historical, so ignore it. An installment calculator tool applies the §3.1 tiers to new quotes. |
| 9 | Product 96 is `active` with stock 0. Product 136 is `discontinued` with stock 13. Product 113 is `discontinued` with stock 0. | Medium | Availability is `status == "active" and stock > 0`. For active products with stock 0, say "temporariamente indisponível" and suggest alternatives (§7.3). For discontinued products, say "fora de catálogo" and suggest alternatives. |
| 10 | Duplicate customer email (IDs 11 and 43). | Medium | Never identify a customer by email alone. Order lookups need `order_id` plus a matching email or phone. |
| 11 | Product 84's name has the typo "Giannini GN-15 Nylon **Cedr** Natural". | Low | Keep the name as-is. Search uses accent-folded, case-insensitive matching on name and description, so "cedro" still matches. |
| 12 | Product names mix accented and unaccented spellings, with English words ("Elétrico", "Barítono", "Cedar"/"Cedro", "Mogno"). | Low | Normalize the search key with NFKD, strip combining marks and casefold. Keep the displayed text unchanged. |
| 13 | Product IDs aren't sorted (145 sits before 131), and the `specs` JSON spacing varies. | Low | Sort by `product_id` on load and parse `specs` into a dict. |
| 14 | `tracking_code`, `estimated_delivery` and `notes` use empty strings for missing values. | Low | Convert `""` to `None`, and parse dates into `date` objects. |
| 15 | `payment_method` packs the method and the installment count into one value (`credit_12x`). | Low | Parse it into `method` (`pix`, `debit`, `credit`, `boleto`) and `installments` (int or None), and map to pt-BR labels for replies. |
| 16 | Categories 6–8 are empty, though the policy says the store sells wind and orchestral string instruments, and it claims "mais de 300 instrumentos" against 65 rows. | Medium | When the catalogue has nothing for a request, say there's nothing available right now. Never invent items. |
| 17 | The CSV file names have a prefix and spaces, plus `Zone.Identifier` artifacts. | Low | Use a loader with an explicit table → file mapping. |
| 18 | Customer cities and order delivery times disagree with the policy. Campo Grande orders (e.g. 1, 4 and 7) have estimated deliveries 10–14 calendar days out, against the policy's 1–3 business days by motoboy. They also carry Correios-format tracking codes, although the policy says motoboy delivery. | Low | Report `estimated_delivery` and the tracking code from the data. Use the policy only for general questions about delivery times. |

## 5. Policy document summary

`políticas_da_loja.pdf`: "Manual de Políticas e Procedimentos – Atendimento ao Cliente", Versão 2.1, Junho de 2025. The metadata title is `políticas_da_loja.docx`, exported from Google Docs.

- **Extraction:** it's a text PDF with no images to OCR and no `U+FFFD` replacement characters. **pypdf's default `extract_text()` is unusable**, though: it emits one word per line, with `"\n \n"` between words. `extract_text(extraction_mode="layout")` gives clean, well-ordered text with headings, bullets and tables preserved as aligned columns. Every page has the header "Empório da Música Manual de Políticas e Procedimentos" and the footer "Página N"; strip both before chunking.
- **Size:** 8 pages, about 1,750 words and about 11.8 K characters after collapsing whitespace, so **roughly 3 K tokens**. Small enough to fit whole in a prompt; the choice to keep RAG anyway is recorded in decision D10.

### Outline
```
(cover) EMPÓRIO DA MÚSICA — Sua música começa aqui. — address, phone, email
1. Sobre a Empório da Música
   1.1 Missão
   1.2 Dados da Empresa            (table: razão social, CNPJ, endereço, telefone/WhatsApp, e-mail, fundação)
2. Horário de Funcionamento        (table)
3. Formas de Pagamento             (table)
   3.1 Regras de Parcelamento
4. Política de Trocas e Devoluções
   4.1 Direito de Arrependimento (Compras Online)
   4.2 Trocas por Defeito
   4.3 Trocas por Preferência
   4.4 Itens Não Elegíveis para Troca
5. Política de Frete e Entregas
   5.1 Entregas na Região Metropolitana de Campo Grande
   5.2 Entregas para Outras Cidades  (table: PAC, SEDEX, Jadlog)
   5.3 Código de Rastreamento
6. Promoções e Descontos
   6.1 Tipos de Promoção
   6.2 Regras de Promoções
7. Atendimento via WhatsApp
   7.1 Diretrizes de Atendimento
   7.2 Fluxo de Atendimento Padrão
   7.3 Situações Especiais
8. Garantia
   8.1 Garantia Legal
   8.2 Garantia do Fabricante
   8.3 O que Não Cobre a Garantia
9. Privacidade e Proteção de Dados
10. Disposições Finais
```

### Topics and key facts
| Topic | Section | Key facts (as written) |
|---|---|---|
| Address | cover, 1.2 | Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, 79202-333 |
| Contacts | cover, 1.2, 7 | Telefone / WhatsApp (67) 3341-4444. §7 gives the WhatsApp as (67) 3321-4500. The email is `contato@emporiodamusica.com.br` on the cover and `contato@empóriodamusica.com.br` in 1.2. |
| Hours | 2 | Segunda a Sexta 09:00 às 18:00; Sábado 09:00 às 13:00; Domingo e Feriados Fechado. Hours may be extended on Black Friday, Aniversário and Natal. |
| Payment | 3 | PIX à vista with 5% off; Débito (todas as bandeiras); Crédito até 12x sem juros (parcela mínima R$ 100,00); Boleto à vista (compensação em até 3 dias úteis). |
| Installments | 3.1 | Up to 3x: no minimum "(exceto abaixo de R$ 50,00)". 4x–6x: minimum R$ 80,00. 7x–12x: minimum R$ 100,00. Combining payment methods is allowed above R$ 2.000,00. |
| Withdrawal (arrependimento) | 4.1 | 7 dias corridos **após o recebimento**, no justification needed. Product must be in its original packaging, unused. Refund by the original payment method within 10 dias úteis. The store pays return shipping. Applies to "Compras Online". |
| Defect exchange | 4.2 | 30 dias corridos **após a compra**. After that, the manufacturer's warranty applies and the store can intermediate. Misuse, falls, humidity and modifications aren't covered. |
| Preference exchange | 4.3 | Within 7 dias (start date not stated), subject to availability. Perfect condition and original packaging required. Price differences are charged or refunded. |
| Not eligible | 4.4 | Customized or setup instruments; liquidation items marked "venda final"; wind-instrument mouthpieces (boquilhas). |
| Shipping, metro | 5.1 | Free above R$ 500,00, otherwise R$ 35,00. 1–3 dias úteis by motoboy; the customer gets a phone call before delivery. |
| Shipping, other cities | 5.2 | PAC 5–12, SEDEX 2–5 and Jadlog 3–8 dias úteis, all with tracking and insurance. Price depends on CEP, weight and size. Large instruments (baterias acústicas, pianos digitais, contrabaixos) may need a special quote. Damaged deliveries must be refused. |
| Tracking | 5.3 | Sent by email and WhatsApp on dispatch. Format: BR + 9 alphanumeric characters + BR. |
| Promotions | 6 | Campaigns: Aniversário (Agosto, 10–25%), Black Friday (Novembro, 15–30% "em todo o catálogo"), Volta às Aulas (Fevereiro), Queima de Estoque, Semana do Músico (around 22 Nov). Promotions don't stack: **the PIX 5% doesn't apply to promotional prices**. No rain checks. Always show the original price and the discount %. |
| Tone and process | 7.1–7.2 | "Informal mas profissional", like a friend who knows music. Never state price, stock or delivery times without checking the system. Accessories are out of scope; redirect politely. Flow: saudação → entendimento → consulta → resposta → fechamento. Response within 5 minutes; outside business hours, say when the team is back. |
| Special situations | 7.3 | Out of stock: say so and suggest alternatives. Discontinued: say so and offer equivalents. Expired promotion: be transparent and give the current price. Complaints: register them and pass them on; reply within 24 horas úteis. |
| Warranty | 8 | Legal warranty: 90 dias **a partir do recebimento**. Manufacturer warranty: 6 meses to 2 anos. Exclusions: wear, misuse, third-party repairs, cosmetic damage. |
| Privacy | 9 | LGPD. Data used only for orders, communication, marketing (with consent) and legal duties. The customer can ask for deletion. |
| Scope | 1, 7.1 | Instruments only. No strings, picks, cables, cases, pedals or amplifiers. |

### Rules that depend on CSV data
| Rule | Data needed | Available? |
|---|---|---|
| Withdrawal 7 days from receipt (4.1) | delivery date | **No**, only `orders.estimated_delivery` |
| Defect exchange 30 days from purchase (4.2) | `orders.order_date` | Yes |
| Legal warranty 90 days from receipt (8.1) | delivery date | **No**, only `estimated_delivery` |
| Preference exchange 7 days, subject to availability (4.3) | start date (unspecified), `products.stock_quantity` | Partly |
| Withdrawal only for "Compras Online" (4.1) | sales channel | **No** channel column; assume all orders are online |
| "Venda final" liquidation items are not eligible (4.4) | link from order to promotion, plus a final-sale flag | **No**. Orders don't record which promotion applied. |
| Customized instruments are not eligible (4.4) | customization flag | **No** |
| PIX 5% off, not on promotional prices (3, 6.2) | `products.price_brl`, current promotion | Yes |
| Installment minimums (3.1) | price | Yes |
| Free metro shipping above R$500 (5.1) | customer address or CEP | Only `customers.city` (Campo Grande = metro, approximately) |
| Special freight for large instruments (5.2) | category | Yes, categories 3, 4 and 2 (if "contrabaixos" means bass guitars) |
| Promotions subject to stock; expired promotions (6.2, 7.3) | `promotions.is_active`, `products.stock_quantity` | Yes, with no dates |
| Out of stock / discontinued handling (7.3) | `products.status`, `stock_quantity` | Yes |
| Tracking format (5.3) | `orders.tracking_code` | Yes, all valid |
| Business hours, "outside business hours" message (2, 7.1) | current time; holiday calendar | Clock only; **no holiday list** |

### Contradictions between the PDF and the CSVs, or within the PDF
1. **Email:** `contato@emporiodamusica.com.br` on the cover, but `contato@empóriodamusica.com.br` (with an accent, which isn't a valid plain-ASCII host) in §1.2.
2. **WhatsApp:** §1.2 says "Telefone / WhatsApp (67) 3341-4444", but §7 says the WhatsApp channel is (67) 3321-4500.
3. **Installment minimums:** the table in §3 says "parcela mínima de R$ 100,00" for credit in general, while §3.1 sets tiers (R$50, R$80, R$100). The ≤3x wording "sem valor mínimo de parcela (exceto abaixo de R$ 50,00)" is self-contradictory. Read it as a minimum installment of R$50.
4. **Return windows start from different events:** 4.1 counts from receipt, 4.2 from purchase and 8.1 from receipt. 4.3 gives no start date.
5. **Campaigns:** CSV campaigns that aren't in the policy are Promoção de Páscoa, Liquidação de Inverno, Oferta Especial and Desconto Exclusivo. Volta às Aulas is in the policy but not in the CSV. Percentages outside the policy's ranges: Aniversário 30% (promotion 17), Black Friday 10% and 25% (promotions 1 and 16, below the stated 15–30% "em todo o catálogo"), and Semana do Músico 40% (promotion 22). All of these are inactive, so this only matters for questions about past promotions.
6. **Catalogue:** the policy claims "mais de 300 instrumentos" and lists wind instruments, orchestral strings and "pianos digitais". The CSV has 65 products, no wind or orchestral items, and only synthesizers in Teclados.
7. **Payment methods:** every method in `orders` (pix, debit, credit_3x/6x/12x, boleto) is in the policy ✓. The 5% PIX discount isn't reflected in PIX order totals, and three orders break the installment minimums (issues 7 and 8).
8. **Delivery:** metro orders show 10–14 day estimates and Correios tracking codes, while the policy says motoboy delivery in 1–3 dias úteis (issue 18).

## 6. Cross-checks with the challenge examples

| Challenge example | Result |
|---|---|
| "Quanto custa o Takamine GD20?" | **Exists:** product 95 "Takamine GD20 Dreadnought Natural", R$ 2.199,00, stock 5, active. Its promotion 4 (Oferta Especial, 12%) is **inactive**, so it's a good test of the "expired promotion" rule. PIX price R$ 2.089,05 (5% off). 12x of R$ 183,25 meets the R$100 minimum. Other Takamines: 100 (R$3299), 105 (R$4199), 115 (R$2499). |
| "Quais opções de violões disponíveis custando até R$1000?" | 14 violões cost ≤ R$1000. **12 are available** (active with stock): 83 Tagima Memphis AC-39 (429.90), 85 Rozini RC-104 (459.90), 89 Shelby SN-100 (549.00), 88 Giannini GF-1R (579.90), 81 Yamaha C40 (599.90), 84 Giannini GN-15 (689.00), 87 Yamaha F310 (699.90), 86 Tagima Dallas Tuner (749.00), 107 Shelby SGD-195E (799.00), 82 Yamaha C70 (849.00), 91 Tagima Woodstock (899.00), 112 Tagima TW-7 (999.00). Excluded: 96 Giannini GF-3D (active, **stock 0**) and 113 Shelby SN-7C (**discontinued**). None has an active promotion. |
| "Qual o endereço da loja?" | Policy §1.2: Rua 14 de Maio, 3200 — Centro, Campo Grande - MS, 79202-333. |
| "Me arrependi da minha compra, posso devolver meu pedido?" | No order is inside the 7-day window today (issue 2). Good examples need a reference-date decision; see the next section. |

## 7. PII notes

| Table.column | Data | Sensitivity | Handling |
|---|---|---|---|
| customers.name | full name | Medium | Show it only to the verified owner. Greet by first name. |
| customers.email | email | High (identifier) | Use it only to verify identity. Never reveal it. Mask it if echoed (`le***@jmail.com`). |
| customers.phone | mobile number | High (identifier) | Same as email. |
| customers.city | city | Low | Used for the shipping rule (metro or not). |
| orders.* | purchase history, amounts, payment method | Medium | Return it only after verification (`order_id` + email or phone). |
| orders.tracking_code | shipment tracking | Medium | Return it only after verification. |
| orders.notes | cancellation reasons | Low–Medium | OK to share with the verified owner. |
| Policy §1.2 | company CNPJ, address, phone | Public business data | OK to share. |

There is no CPF, street address, birth date or payment card data. All emails use fictional domains, so this is synthetic data, but the agent should still be built as if the PII were real (LGPD, policy §9). Only the fields a tool needs should reach the LLM. In particular, never pass customer lists to the model.

## 8. Candidate records for the example conversations

Every return-window figure below uses `estimated_delivery` as the receipt date.

**Return policy, outside the window (works with the real date, 2026-10-27):**
- Order **7**: customer 14 Letícia Gonçalves Rocha (`leticia.rocha@jmail.com`, (67) 99789-0123), delivered, ordered 2026-02-03, received 2026-02-17 (estimated), 1× Shelby SU-21S Soprano Sunburst (R$159.90, credit_3x). It's 252 days after receipt, so withdrawal (7 days), defect exchange (30 days from purchase) and the legal warranty (90 days) have all expired. The agent should explain this kindly and point to the manufacturer's warranty (6 months to 2 years, §8.2).
- Order **1**: customer 3 Pedro Henrique Oliveira, 1× Martin D-28 (R$11,499, PIX), received 2025-10-25. A high-value example of an expired window.

**Return policy, inside the window (needs a reference date, e.g. `STORE_TODAY=2026-02-20`):**
- Order **7** is then 3 days after receipt, **inside** the 7-day withdrawal window.
- Order **6** (customer 9 Gabriel Santos Araújo, Dourados, Taylor 214ce R$7,499, received 2026-02-01) is then 19 days after receipt, **outside** the withdrawal window. It's 33 days after purchase, so also outside the 30-day defect exchange, but **inside** the 90-day legal warranty, which shows the rules layering.
- The catch: orders 10–16, 19 and 20 are dated after 2026-02-20, so they'd be in the "future". The tool can treat them as not yet relevant, or the demo can just use a different date for each scenario.

**Order status:**
- Order **8**: customer 2 Ana Carolina Ferreira, `shipped`, tracking BRJL5544332BR, estimated 2026-02-28 (late against the real date). It also shows that the withdrawal window hasn't started before receipt.
- Order **13**: customer 8 Fernanda Ribeiro Souza, `pending`, PIX, R$1,899.
- Order **17**: `cancelled`, note "Pedido cancelado pelo cliente antes do processamento".

**Price, promotion and availability:**
- Promotion applied: 121 Ohana CK-20 Concert Natural, R$549.00 → R$439.20 (20%, Desconto Exclusivo). Show the original price and the %, and don't add the PIX 5% (§6.2).
- Expired promotion: 95 Takamine GD20 (promotion 4 inactive) or 91 Tagima Woodstock (Black Friday 30%, inactive).
- Out of stock: 96 Giannini GF-3D Dreadnought Sunburst (active, stock 0). Suggest similar dreadnoughts ≤ R$1000 (91 Tagima Woodstock).
- Discontinued: 113 Shelby SN-7C 7 Cordas. Suggest 112 Tagima TW-7 or 110 Giannini GWNE-7.
- Coming soon: 130 Kala KA-ABP-CTG Barítono Cedar.
- Installments: 81 Yamaha C40 at R$599.90 allows up to 6x (R$99.98 ≥ 80) but not 7x (R$85.70 < 100).

**Out of scope:** "Vocês vendem cordas / pedal / amplificador?" The store sells instruments only (§1, §7.1). Also anything off-topic.

**Empty category:** "Tem saxofone?" Category 6 exists but has no products, so say nothing is available and don't invent any.

## 9. Resolved decisions

The open questions raised by this inventory, resolved on 2026-10-27. None of them changes `data/`; every rule is applied in code, settings or documentation, and each assumption goes into the README.

### D1. Return-window reference date
- For `delivered` orders, `estimated_delivery` is treated as the receipt date. For `shipped` orders the receipt date is unknown, so receipt-based windows (§4.1, §8.1) have not started.
- "Today" comes from an optional `STORE_TODAY` setting and falls back to the system date.
- `.env.example` suggests `STORE_TODAY=2026-03-23`, the day after the last order and so the effective snapshot date of the data. On that date no order is in the future, pending orders are plausible, and order 7 shows the rules layering: 34 days after receipt (withdrawal expired), 48 days after purchase (defect exchange expired), inside the 90-day legal warranty.
- The "inside the window" example is recorded with `STORE_TODAY=2026-02-20` (order 7, 3 days after receipt), and the date is stated in the example's header.
- Guard: if `order_date > today`, the order tool reports the order but computes no window for it.

### D2. Promotions without dates
- `is_active == 1` is the only source of truth for promotions.
- A promotion is current only when the product is also `active` with stock > 0 (§6.2). Today all 4 active promotions (products 90, 94, 121, 127) have stock, so this is a safety net.
- A test asserts that no product has more than one current promotion.

### D3. Canonical contacts
Resolved as a cleaning step at policy ingestion:
- Email: `contato@emporiodamusica.com.br`. The accented form in §1.2 is treated as a typo.
- Phone: (67) 3341-4444 (cover and §1.2).
- WhatsApp: (67) 3321-4500. §7 is the section dedicated to the WhatsApp channel, so the more specific section wins.

### D4. Products 135–144
- Kept in the catalogue: order 10 contains product 135, so removing them would break order lookups.
- Only name, price, availability and status are shown. Description and specs are never quoted.
- The IDs live in an explicit set in the cleaning module, with a comment explaining why and a test.

### D5. Product status in search results
- The search tool takes `only_available: bool = True`. List and price-filter queries return only buyable products (`active` and stock > 0).
- Lookup by name returns any status with a label: "em breve" (`coming_soon`), "fora de catálogo" (`discontinued`) or "temporariamente indisponível" (`active`, stock 0), followed by alternatives (§7.3).

### D6. Customer verification
- Order data is shown only for `order_id` plus an email or phone that matches that order's customer. Because the check is per order, the shared email of customers 11 and 43 doesn't matter (customer 43 has no orders).
- There is no "list my orders by email" feature.
- Contact details are masked in replies, and only the fields a tool needs reach the LLM.

### D7. Cancellation and other change requests
- All tools are read-only.
- For a cancellation request, the agent explains the order's current status, says the policy doesn't cover self-service cancellation, and hands off to the team with the WhatsApp number and business hours. It never promises a cancellation or a refund.
- Withdrawal and exchange requests work the same way: the agent explains whether the order qualifies, and the team handles the logistics.

### D8. Installment tiers
- Minimum installment: 1–3x R$50, 4–6x R$80, 7–12x R$100; 12x is the maximum. 1x is always allowed.
- The R$100 in the §3 table is read as the 12x headline, not a general rule. With the cheapest product at R$159.90 (3× R$53.30), the R$50 floor never binds today.

### D9. Shipping quotes
- Prices are quoted only for the metro rule: Campo Grande, free above R$500, otherwise R$35 (§5.1).
- For other cities the agent gives the PAC, SEDEX and Jadlog time ranges, says the price depends on CEP, weight and size, and hands off for a quote (§5.2).
- Drums, keyboards and basses are flagged as possibly needing a special quote. The agent doesn't ask for a CEP, since no tool can use it.

### D10. Policy retrieval: RAG over the PDF
The policy is about 3 K tokens, so putting it whole in the system prompt would work and is simpler. RAG is kept anyway, because:
- The challenge asks for a justified retrieval architecture, and RAG behind a `search_policies` tool keeps "when to consult policies" an explicit agent decision, separate from "when to consult data".
- Heading-aware chunks (one per subsection, about 25 chunks, no overlap needed since subsections are self-contained) let the agent cite the section it used.
- It scales if the manual grows, and keeps the system prompt short and stable.

Trade-off: retrieval can miss a relevant section that full context would always include. This is mitigated with retrieval tests on known questions and listed as a known limitation in the README, with full-context prompting as the alternative.

### D11. Example conversations
The 5 conversations to record (challenge deliverable 3), with the data they exercise:

| # | Scenario | Records | What it shows |
|---|---|---|---|
| 1 | "Quais opções de violões disponíveis custando até R$1000?" | 12 available violões (83, 85, 89, 88, 81, 84, 87, 86, 107, 82, 91, 112) | Catalogue search with filters; 96 (stock 0) and 113 (discontinued) excluded |
| 2 | "Quanto custa o Takamine GD20?" | Product 95, R$ 2.199,00, promotion 4 inactive | Price lookup, PIX price (R$ 2.089,05), installments (12x R$ 183,25), expired promotion handled transparently |
| 3 | "Qual o endereço da loja? Que horas vocês abrem no sábado?" | Policy §1.2 and §2 | Policy retrieval with section citation |
| 4 | "Me arrependi da minha compra, posso devolver meu pedido?" | Order 7, customer 14 (verified by order ID + email) | Verification, then layered return rules: inside the withdrawal window at `STORE_TODAY=2026-02-20`, outside it at `2026-03-23` |
| 5 | "Vocês vendem cordas? E saxofone?" | Policy §1 and §7.1; category 6 with no products | Out-of-scope redirect and an empty category without inventing items |

Order 8 (shipped, estimated delivery 2026-02-28, now late) is the reserve for an order-status example.
