# Database ng Vista VMS: isang file, i-import sa PostgreSQL

**`vista_database.sql`** ang kailangan mo. Laman nito:
- 23 table ng system (buo, galing sa 10 migration), at
- ang demo village na **Greenfield Village** para sa pag-test: 5 staff account, 6 bahay, 3 gate, 9 bisita.

Kapag totoong gamit na, **isang command** lang ang magtatanggal ng demo data (nasa ibaba).

Kailangan: PostgreSQL 13 pataas (nasubok sa 16). May `pgcrypto` ito sa karaniwang installer. Gamitin ang `postgres` user (o ang owner ng database) sa pag-import.

## 1. I-import (pgAdmin)

1. I-right-click ang **Databases > Create > Database**. Pangalan: `vista`. **Dapat bago at walang laman.**
2. I-click ang `vista`, tapos **Tools > Query Tool**.
3. I-click ang **Open File** (folder icon) at piliin ang `vista_database.sql`.
4. Pindutin ang **F5**. Mga ilang segundo lang. Dapat sabihin: "Query returned successfully".
5. I-right-click ang `vista` > **Refresh**. Sa **Schemas > public > Tables** dapat may **23 table**.

> Huwag gamitin ang "Restore" ng pgAdmin. Plain SQL ang file na ito, kaya Query Tool ang tama.

Command line, kung gusto:
```
createdb -U postgres vista
psql -U postgres -d vista -f database/vista_database.sql
```

## 2. Ikonekta ang system

Sa API, ilagay ang:
```
DATABASE_URL=postgresql://postgres:ANG_PASSWORD@localhost:5432/vista
AUTO_SEED=0
```
- Gamitin ang **parehong user** na nag-import. Ang mga table ay pag-aari ng nag-import, at kapag ibang user ang gamit ng app, haharangin ito ng row-level security at walang lalabas na data.
- Kung may espesyal na character ang password (`@ : / # ?`), i-URL-encode ito (`@` ay `%40`). Ginagawa ito ng `start-nodocker.bat/.sh` para sa iyo.
- `AUTO_SEED=0` kasi nasa file na ang demo data. Sa `start-nodocker`, sagutin ng `N` ang tanong tungkol sa demo.
- Puwedeng iwanang naka-on ang `AUTO_MIGRATE=1`: nasubok kong wala itong ginagawa sa database na na-import na.

## 3. Mag-test (demo)

Sundin ang `START-HERE.md` at `CHECKLIST.md`. Mga account (password `VistaDemo2026!`): `ramon@greenfield.ph` (guard), `lorna@greenfield.ph` (HOA), `admin@greenfield.ph` (Admin).

Ang mga petsa ng demo bisita ay ayon sa araw na ginawa ang file, kaya kung ilang araw na ang lumipas, mas luma na ang "Today" na listahan.

## 4. Totoong gamit: tanggalin ang demo

Sa pgAdmin Query Tool (sa database na `vista`), patakbuhin:
```sql
SELECT public.vista_remove_demo();
```
Mabubura ang demo village at lahat ng nakakabit dito (account, bahay, bisita, litrato, alerto, audit). **Mananatili ang mga table.** Hindi nito ginagalaw ang ibang village na ginawa mo, nasubok ko ito: gumawa ako ng totoong village habang nandoon pa ang demo, binura ko ang demo, at natira ang totoong village at ang Admin nito.

Pagkatapos, gumawa ng sarili mong village:
1. Patakbuhin ang API na may `SUPER_ADMIN_CODE=<code mo>`.
2. Buksan ang http://localhost:5173/ > **Platform owner? Super Admin sign-in** > ilagay ang code.
3. **New property:** pangalan ng village, pangalan at email ng Admin. Lalabas ang village link.
4. Pindutin ang **Admin link** at buksan ito: papasok ka bilang Admin. Pindutin ang **Change password** at maglagay ng sariling password (hindi kailangan ng current sa unang beses).
5. Gumawa ng mga account ng guard at HOA sa **Guards and HOA office > Add account** (lagyan ng password).
6. Idagdag ang mga bahay sa **Households** at i-verify ang bawat isa.

Kapag tapos na, puwede mo ring alisin ang function: `DROP FUNCTION public.vista_remove_demo();`

## Mga karaniwang problema

| Mensahe | Ibig sabihin |
|---|---|
| `relation "..." already exists` | Hindi walang laman ang database. Gumawa ng bagong database at ulitin. |
| `permission denied to create extension "pgcrypto"` | Gamitin ang `postgres` user, o patakbuhin muna: `CREATE EXTENSION IF NOT EXISTS pgcrypto;` |
| Naka-sign in pero walang data | Ibang user ang gamit ng API kaysa sa nag-import (tingnan sa itaas). |
| `database "vista" does not exist` | Hindi pa nagagawa ang database sa hakbang 1. |
| `Unknown property` pagkatapos tanggalin ang demo | Normal: wala na ang `greenfield-village-7f3a`. Gamitin ang village link ng bago mong village. |

**Babala:** may kilalang password (`VistaDemo2026!`) ang mga demo account. **Huwag mag-publish nang hindi pa nakakapatakbo ng `vista_remove_demo()`.**
