# Raport ewaluacji abstynencji i jakości odpowiedzi (Sprawdzian 1b i 2a)

> [!WARNING]
> **Fallback `EVAL_JUDGE_MODEL`**: Nie skonfigurowano osobnego modelu sędziego — użyto modelu odpowiedzi (`gemini-3.5-flash-lite`). Wyniki sędziego mogą być obciążone stronniczością self-preference.

## Metadane i odtwarzalność

| Parametr | Wartość |
| --- | --- |
| Nazwa przebiegu | `abstention-test-20261126T152210Z` |
| Czas przebiegu (UTC) | `2026-11-26T15:22:10.457270+00:00` -> `2026-11-26T15:24:34.302941+00:00` |
| Split / limit / współbieżność | `test` / `None` / `3` |
| Migawka / rewizja | `techqa@0b5bbc84b7f07d6d09d063130e90b716d8d4a32a` / `0b5bbc84b7f07d6d09d063130e90b716d8d4a32a` |
| Zestaw fragmentów / wariant | `techqa@0b5bbc84b7f07d6d09d063130e90b716d8d4a32a/sections-v1` / `sections-v1` |
| Hash konfiguracji chunkera (`config_sha256`) | `27e96744ecf5e7175087a662ee175a601333b23e2dcd9c2fda41704595fa5b7c` |
| Hash stanu fragmentów (`state_sha256`) | `3981ae29e8406ad9fbb59591d77f5babee768f733d76ca0ac35b26f0414b8eb9` |
| Hash `train.json` (`train_json_sha256`) | `69d97231509482ed6bd5ec1c4bc0607acb82a88d11169eb8383592d0ca8b93c7` |
| Ziarno / proporcja splitu (`dev_ratio`) | `20261125` / `0.3` |
| Zbiór etykiet (łącznie / ambiguous / aktywne) | `140` / `26` / `114` |
| Model odpowiedzi | `gemini-3.5-flash-lite` (reasoning: `low`, `k=8`) |
| Wersje promptów odpowiedzi | `draft=8260994ea7b1`, `verify=1722963887da` |
| Model sędziego | `gemini-3.5-flash-lite` (reasoning: `low`, fallback: `True`) |
| Wersje promptów sędziego | `citation_support=f545f12c645f`, `reference_agreement=2000dcc1d3f5` |
| Hash konfiguracji przebiegu (`config_sha256`) | `759d5f824f7f8366f59a73dad284b9552b05f18688b72292e21073c33984f16e` |
| Langfuse Cloud (`experiment_id` / URL) | `43bf66331ca84f95` (https://cloud.langfuse.com/project/cmwvw8e6b005sad0j1e1fcunw/experiments/results?baseline=43bf66331ca84f95) |

## Podsumowanie Sprawdzianu 2a (Abstencja i fałszywe odmowy)

| Metryka | Wartość | Próba |
| --- | --- | --- |
| Trafność abstencji (`abstention_accuracy`) | **76.1%** | `n=46` (`verified_unanswerable`) |
| Odsetek fałszywych odmów (`false_refusal_rate`) | **25.0%** | `n=68` (`answerable_in_corpus`) |
| Ocenione / odpowiedzi / abstencje | `114` / `62` / `52` | `n_total=114` |
| Błędy wykonania (`n_failed`, poza mianownikami) | `0` | `n_total=114` |

## Podsumowanie Sprawdzianu 1b (Cytaty, zgodność z referencją i opóźnienie)

| Metryka | Wartość |
| --- | --- |
| Zgodność z inwariantami cytatów (`citation_invariants_pass_rate`) | 100.0% |
| Wsparcie cytatów — poziom tezy (`citation_support_claim_rate`) | 97.4% |
| Wsparcie cytatów — pełne odpowiedzi (`citation_support_answer_rate`) | 96.8% |
| Zgodność z odpowiedzią referencyjną (`reference_agreement_mean`) | 0.571 (`full=9`, `partial=14`, `incorrect=5`) |
| Opóźnienie grafu S-02 `p50` / `p95` | 1670 ms / 2303 ms |
| W budżecie opóźnienia (`< 10000 ms`) | 100.0% |
| Błędy wykonania (`n_failed`) / błędy sędziego (`n_judge_failed`) | `0` / `0` |

## Rozbicie przyczyn abstencji

| Przyczyna | Liczba |
| --- | --- |
| `no_hits` | `0` |
| `no_claims` | `50` |
| `quote_check_rejected_all` | `1` |
| `verify_rejected_all` | `1` |

## Przykłady błędów

### Błędne odpowiedzi na pytania bez odpowiedzi (missed abstentions)
- `DEV_Q009` (`test`) — tezy=1, cytaty=1; sędzia cytatów: 1/1 supported
- `DEV_Q036` (`test`) — tezy=1, cytaty=1; sędzia cytatów: 1/1 supported
- `DEV_Q065` (`test`) — tezy=1, cytaty=1; sędzia cytatów: 1/1 supported
- `DEV_Q091` (`test`) — tezy=1, cytaty=1; sędzia cytatów: 1/1 supported
- `DEV_Q148` (`test`) — tezy=1, cytaty=1; sędzia cytatów: 1/1 supported
- `DEV_Q166` (`test`) — tezy=1, cytaty=1; sędzia cytatów: 1/1 supported
- `DEV_Q190` (`test`) — tezy=2, cytaty=1; sędzia cytatów: 2/2 supported
- `DEV_Q203` (`test`) — tezy=1, cytaty=1; sędzia cytatów: 1/1 supported
- `DEV_Q223` (`test`) — tezy=1, cytaty=1; sędzia cytatów: 1/1 supported
- `DEV_Q274` (`test`) — tezy=1, cytaty=1; sędzia cytatów: 0/1 supported
- …oraz 1 kolejnych przypadków w surowym pliku JSON.

### Fałszywe odmowy (false refusals)
- `DEV_Q000` (`test`) — przyczyna abstencji: `no_claims`
- `DEV_Q007` (`test`) — przyczyna abstencji: `no_claims`
- `DEV_Q011` (`test`) — przyczyna abstencji: `no_claims`
- `DEV_Q022` (`test`) — przyczyna abstencji: `no_claims`
- `DEV_Q023` (`test`) — przyczyna abstencji: `no_claims`
- `DEV_Q027` (`test`) — przyczyna abstencji: `no_claims`
- `DEV_Q028` (`test`) — przyczyna abstencji: `no_claims`
- `DEV_Q034` (`test`) — przyczyna abstencji: `no_claims`
- `DEV_Q039` (`test`) — przyczyna abstencji: `no_claims`
- `DEV_Q047` (`test`) — przyczyna abstencji: `no_claims`
- …oraz 7 kolejnych przypadków w surowym pliku JSON.

## Walidacja ręczna sędziego

| Metryka walidacji | Wartość |
| --- | --- |
| Próbka / ocenione ręcznie | `20` / `20` |
| Zgodność sędziego cytatów (procent / Cohen's kappa) | 93.3% / 0.000 (`n=15`) |
| Zgodność sędziego referencji (procent / Cohen's kappa) | 66.7% / 0.500 (`n=6`) |

### Macierz pomyłek — wsparcie cytatów

| Sędzia \ Człowiek | `supported` | `unsupported` |
| --- | --- | --- |
| `supported` | `14` | `0` |
| `unsupported` | `1` | `0` |

### Macierz pomyłek — zgodność z odpowiedzią referencyjną

| Sędzia \ Człowiek | `full` | `partial` | `incorrect` |
| --- | --- | --- | --- |
| `full` | `2` | `1` | `0` |
| `partial` | `0` | `1` | `1` |
| `incorrect` | `0` | `0` | `1` |

### Przegląd jakościowy warstwy `abstained`

- W próbce: `5`, ocenione ręcznie: `5` (uzasadnione: `4`, nieuzasadnione: `1`).

## Ograniczenia

- Przypadki `failed` (przekroczenie `answer_deadline_s` lub błąd grafu) są wykluczone z mianowników metryk jakości i percentyli opóźnień `p50`/`p95` i raportowane osobno jako `n_failed`.
- Pomiar `latency_ms` obejmuje wyłącznie wykonanie grafu odpowiedzi S-02 (od `retrieve` do `compose`/`abstain`), bez czasu wywołań sędziego LLM.
- Ocena dotyczy pojedynczego wariantu wyszukiwania BM25 (`k=8`) na zamrożonej migawce `techqa@0b5bbc84b7f07d6d09d063130e90b716d8d4a32a`; pytania oznaczone jako `ambiguous` (`26`) zostały wykluczone z aktywnej próby.
- Metryki wsparcia cytatów i zgodności z odpowiedzią referencyjną opierają się na sędzim LLM i wymagają okresowej walidacji ręcznej.
- **Przejrzystość przeglądu (`[AI review]` / `[AI blind review]`)**: Weryfikację 140 kandydatów `is_impossible=True` względem top-10 trafień BM25 oraz ślepy przegląd 20 wylosowanych pozycji z przebiegu bazowego (bez dostępu do werdyktów sędziego LLM) wykonał agent AI na polecenie operatora. Przed podejmowaniem decyzji produktowych warto potwierdzić losową podpróbkę etykiet i ocen przez człowieka oraz skonfigurować osobny `EVAL_JUDGE_MODEL` (w tym biegu zadziałał jawny fallback na `CHAT_MODEL`).
- **Bieg próbny `dev`**: Poprzedzający przebieg na splicie `dev` (`abstention-dev-20261126T151611Z`, Langfuse `3eb0d28e52114b18`, `n=47`, `failed=0`) uzyskał `abstention_accuracy = 95.0%` (`n=20`) oraz `false_refusal_rate = 25.9%` (`n=27`).
