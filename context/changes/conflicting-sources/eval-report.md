# Raport Sprawdzianu 2b: Wykrywanie sprzecznych źródeł (S-07)

## Metadane i odtwarzalność

| Parametr | Wartość |
| --- | --- |
| Nazwa przebiegu | `conflicts-20261126T200356Z` |
| Czas przebiegu (UTC) | `2026-11-26T20:03:56.995824+00:00` -> `2026-11-26T20:04:31.253438+00:00` |
| Limit / współbieżność | `None` / `2` |
| Migawka TechQA / zestaw fragmentów | `techqa@0b5bbc84b7f07d6d09d063130e90b716d8d4a32a` / `techqa@0b5bbc84b7f07d6d09d063130e90b716d8d4a32a/sections-v1` |
| Hash stanu TechQA (`state_sha256`) | `3981ae29e8406ad9fbb59591d77f5babee768f733d76ca0ac35b26f0414b8eb9` |
| Migawka syntetyczna / zestaw fragmentów | `synthetic@v1` / `synthetic@v1/sections-v1` |
| Hash stanu syntetycznego (`state_sha256`) | `b8252e4418000281a74f418ff803f45f936370d9b5e57cf98525472f7f1f763b` |
| Zbiór przypadków (`dataset_sha256`) | `fbce078a3e06f3a3481c6fbbe6d6e3e6d645b0624da2556f948880d17d14c514` (`n=24`: `contradiction=8`, `different_recommendations=8`, `answered=8`) |
| Model odpowiedzi | `gemini-3.5-flash-lite` (reasoning: `low`, `k=8`) |
| Wersje promptów odpowiedzi | `detect_conflict=10f95a14b3b1`, `draft=ff63073052c6`, `verify=1722963887da` |
| Hash konfiguracji przebiegu (`config_sha256`) | `4c156c55f9c6236fa4a939beb454f9cef57837551023ecbef9b661490e5498a4` |
| Langfuse Cloud (`experiment_id` / URL) | `f10a783e14dfd673` (https://cloud.langfuse.com/project/cmwvw8e6b005sad0j1e1fcunw/experiments/results?baseline=f10a783e14dfd673) |

## Podsumowanie metryk (Sprawdzian 2b)

| Metryka | Wartość | Próba / uwaga |
| --- | --- | --- |
| Trafność stanu (`overall_state_accuracy`) | **75.0%** | `n=24` (`n_failed=0`) |
| Rozróżnienie zakresu (`scope_distinction_accuracy`) | **68.8%** | `n=16` (pary konfliktowe) |
| Różne wersje błędnie jako `contradiction` (`different_version_misclassified_as_contradiction`) | **`0`** | cel: `0` (`n=6`) |
| Odsetek fałszywych konfliktów (`false_conflict_rate`) | **0.0%** | `n=8` (grupa kontrolna `answered`) |
| Cytaty po obu stronach A i B (`both_sides_cited_rate`) | **100.0%** | wyniki `conflicting` |
| Inwarianty cytatów (`citation_invariants_pass_rate`) | **100.0%** | dosłowny wycinek `[quote_start, quote_end)` (A, B i `answered`) |
| Opóźnienie grafu `p50` / `p95` | 2958 ms / 3865 ms | w budżecie `< 10000 ms`: 100.0% |
| Zużycie tokenów (łącznie) | `total=127260` | `input=114507`, `output=12249` |

## Macierz pomyłek (4 klasy)

| Oczekiwane \ Przewidziane | `contradiction` | `different_recommendations` | `answered` | `abstained` |
| --- | --- | --- | --- | --- |
| `contradiction` | `5` | `0` | `3` | `0` |
| `different_recommendations` | `0` | `6` | `2` | `0` |
| `answered` | `0` | `0` | `7` | `1` |
| `abstained` | `0` | `0` | `0` | `0` |

## Przegląd przypadków (bez surowych tekstów TechQA)

| ID | Oczekiwane | Przewidziane | Strony / dokumenty | Inwarianty | Czas |
| --- | --- | --- | --- | --- | --- |
| `CONFLICT-CONTRA-01` | `contradiction` | `answered` | `SYN-KB-0101`, `swg21612023` | `PASS` | 3870 ms |
| `CONFLICT-CONTRA-02` | `contradiction` | `contradiction` | `SYN-KB-0104` vs `SYN-KB-0103` | `PASS` | 3834 ms |
| `CONFLICT-CONTRA-03` | `contradiction` | `contradiction` | `SYN-KB-0106` vs `SYN-KB-0105` | `PASS` | 3282 ms |
| `CONFLICT-CONTRA-04` | `contradiction` | `contradiction` | `SYN-KB-0108` vs `SYN-KB-0107` | `PASS` | 2931 ms |
| `CONFLICT-CONTRA-05` | `contradiction` | `contradiction` | `SYN-KB-0110` vs `SYN-KB-0109` | `PASS` | 3301 ms |
| `CONFLICT-CONTRA-06` | `contradiction` | `answered` | `SYN-KB-0111`, `swg21681687` | `PASS` | 3105 ms |
| `CONFLICT-CONTRA-07` | `contradiction` | `answered` | `SYN-KB-0113` | `PASS` | 2074 ms |
| `CONFLICT-CONTRA-08` | `contradiction` | `contradiction` | `SYN-KB-0115` vs `SYN-KB-0116` | `PASS` | 3064 ms |
| `CONFLICT-DIFF-01` | `different_recommendations` | `different_recommendations` | `SYN-KB-0007` vs `swg21648497` | `PASS` | 2986 ms |
| `CONFLICT-DIFF-02` | `different_recommendations` | `different_recommendations` | `SYN-KB-0008` vs `swg21632275` | `PASS` | 3203 ms |
| `CONFLICT-DIFF-03` | `different_recommendations` | `answered` | `SYN-KB-0009` | `PASS` | 1726 ms |
| `CONFLICT-DIFF-04` | `different_recommendations` | `different_recommendations` | `swg27041734` vs `SYN-KB-0010` | `PASS` | 4117 ms |
| `CONFLICT-DIFF-05` | `different_recommendations` | `different_recommendations` | `SYN-KB-0011` vs `swg21615234` | `PASS` | 3133 ms |
| `CONFLICT-DIFF-06` | `different_recommendations` | `different_recommendations` | `SYN-KB-0012` vs `swg21644878` | `PASS` | 3056 ms |
| `CONFLICT-DIFF-07` | `different_recommendations` | `answered` | `swg21669900` | `PASS` | 2214 ms |
| `CONFLICT-DIFF-08` | `different_recommendations` | `different_recommendations` | `SYN-KB-0014` vs `swg21695453` | `PASS` | 3508 ms |
| `CONFLICT-ANS-01` | `answered` | `answered` | `swg21606288` | `PASS` | 1511 ms |
| `CONFLICT-ANS-02` | `answered` | `answered` | `swg21620532` | `PASS` | 1942 ms |
| `CONFLICT-ANS-03` | `answered` | `answered` | `swg21623144` | `PASS` | 1662 ms |
| `CONFLICT-ANS-04` | `answered` | `answered` | `swg21625059` | `PASS` | 1776 ms |
| `CONFLICT-ANS-05` | `answered` | `abstained` | brak | `n/d` | 1099 ms |
| `CONFLICT-ANS-06` | `answered` | `answered` | `swg21648606` | `PASS` | 1713 ms |
| `CONFLICT-ANS-07` | `answered` | `answered` | `swg21663283` | `PASS` | 1600 ms |
| `CONFLICT-ANS-08` | `answered` | `answered` | `swg21668433` | `PASS` | 1629 ms |

## Błędy i rozbieżności

- `CONFLICT-CONTRA-01`: oczekiwano `contradiction`, otrzymano `answered` (`same_scope: DB2 LUW 10.5 on Linux, DB2 Linux administrators (unlimited vs 524288 KB)`)
- `CONFLICT-CONTRA-06`: oczekiwano `contradiction`, otrzymano `answered` (`same_scope: WebSphere MQ 8.0 on Unix, MQ administrators (create queue vs do not create queue)`)
- `CONFLICT-CONTRA-07`: oczekiwano `contradiction`, otrzymano `answered` (`same_scope: DB2 LUW 10.5 HADR with TSAMP on Linux, DB2 HA administrators (dedicated ServiceIP vs single shared ServiceIP)`)
- `CONFLICT-DIFF-03`: oczekiwano `different_recommendations`, otrzymano `answered` (`different_version: WAS 8.5.x (TechQA sets false) vs WAS 9.0 (SYN-KB-0009 requires true)`)
- `CONFLICT-DIFF-07`: oczekiwano `different_recommendations`, otrzymano `answered` (`different_version: PathWAI Editor (TechQA recommends 32-bit Oracle Java 7) vs PathWAI Editor 8.0 (SYN-KB-0013 requires 64-bit OpenJDK 11)`)
- `CONFLICT-ANS-05`: oczekiwano `answered`, otrzymano `abstained` (`control_no_conflict: single TechQA technote swg21645009 (security.xml / logoutConfig)`)

## Ograniczenia danych syntetycznych

- Zestaw Sprawdzianu 2b (`n=24`) opiera się na autorskiej nakładce syntetycznej `synthetic@v1` zakotwiczonej tematycznie w prawdziwych dokumentach TechQA — nie pochodzi z rzeczywistych sprzeczności odkrytych w produkcji.
- Wszystkie 8 przypadków `contradiction` zestawia pary dokumentów syntetycznych o jawnych, identycznych metadanych (`product_version`, `audience`), ponieważ dokumenty TechQA nie mają strukturalnych pól wersji ani odbiorcy (`NULL`), a deterministyczny strażnik `resolve_conflict_type()` celowo degraduje pary z rozbieżnymi lub jednostronnie określonymi metadanymi do `different_recommendations` (natomiast pary dwóch dokumentów TechQA bez metadanych opierają się na ocenie `scope_relation` z treści w kroku `detect_conflict`).
- Próba liczy 24 przypadki (po 8 na klasę) i używa pojedynczego mechanizmu wyszukiwania BM25 (`k=8`), więc przedział ufności pojedynczych wskaźników jest szeroki; wynik służy jako bramka regresyjna mechanizmu `detect_conflict` i strażnika zakresu.
