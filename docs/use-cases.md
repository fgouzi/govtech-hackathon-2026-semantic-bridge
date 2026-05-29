# Demo Use Cases

## Use Case 1 — Swiss Government Dataset Reconciliation

**Scenario:** Two Federal Statistical Office (BFS) datasets need to be reconciled.

- `data/swiss/communes.csv` — BFS commune register: `bfs_nr, gemeinde_name, kanton_kuerzel, plz, einwohner_2020`
- `data/swiss/population.csv` — Population stats: `gemeinde_id, name_de, name_fr, total_bevoelkerung, reference_year`

**Goal:** Map each dataset's fields to shared I14Y concepts, then generate a transformation plan to produce a unified view.

**Demo steps in Streamlit UI:**

1. **Upload** (`page 1`) → upload `communes.csv` → schema detected automatically
   - `bfs_nr` → INTEGER, `gemeinde_name` → STRING, `plz` → INTEGER
2. **Explore** (`page 2`) → browse I14Y concepts, search "municipality" → see `Address.Municipality`, `BFS.MunicipalityNumber`
3. **Matching** (`page 3`) → click "Match Schema" → results in ~2s:
   - `bfs_nr` → `BFS.MunicipalityNumber` (confidence: 0.92)
   - `gemeinde_name` → `Address.Municipality` (confidence: 0.88)
   - `kanton_kuerzel` → `Address.CantonCode` (confidence: 0.85)
   - `plz` → `Address.PostalCode` (confidence: 0.79)
4. **Review** (`page 4`) → accept all, AI explanation shown for each mapping
5. **Transform Preview** (`page 5`) → side-by-side original vs transformed records
6. **Validation** (`page 6`) → ✅ no errors, ⚠️ 1 warning: `plz` type ambiguity

**Expected AI explanation:**
> "The field `gemeinde_name` maps to `Address.Municipality` with high confidence (0.88).
> This I14Y concept represents the official German name of a Swiss commune as defined
> by the BFS commune register standard."

---

## Use Case 2 — Enterprise HR ↔ CRM Integration

**Scenario:** A company wants to merge employee records with CRM contacts to identify overlapping persons.

- `data/enterprise/hr_employees.csv` — `emp_id, full_name, birth_date, hire_date, department, salary_chf, office_zip`
- `data/enterprise/crm_contacts.csv` — `contact_id, display_name, date_of_birth, company_name, email, postal_code, revenue_chf`

**Goal:** Map both schemas to shared I14Y Person/Address concepts, generate join key recommendation.

**Matching results:**

| HR field | CRM field | I14Y concept | Confidence |
|---|---|---|---|
| `full_name` | `display_name` | `Person.FullName` | 0.94 / 0.91 |
| `birth_date` | `date_of_birth` | `Person.DateOfBirth` | 0.96 / 0.95 |
| `office_zip` | `postal_code` | `Address.PostalCode` | 0.83 / 0.86 |
| `emp_id` | `contact_id` | `Identifier.LocalID` | 0.71 / 0.69 |

**AI recommendation:**
> "Both schemas share `Person.DateOfBirth` and `Address.PostalCode` as high-confidence
> common concepts. Recommended join key: `Person.DateOfBirth` + `Address.PostalCode`.
> Note: `salary_chf` and `revenue_chf` have no shared I14Y concept — these are
> organisation-specific attributes."

**CLI equivalent:**
```bash
uv run semantic-bridge match data/enterprise/hr_employees.csv --output out/hr_mapping.json
uv run semantic-bridge match data/enterprise/crm_contacts.csv --output out/crm_mapping.json
uv run semantic-bridge validate out/hr_mapping.json
```
