# Jev Ultrafast MCP

Serwer MCP w Pythonie oparty na [browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast).
Każde zadanie uruchamia osobny Chromium **headless**, bez okien i bez profilu użytkownika.

- **JEV przez TypeSafe** wybiera operację i element strony w jednym zapytaniu.
- **GPT-6 Luna przez OpenAI Responses API** generuje wartość pola wyłącznie przy `TYPE_TEXT`.
- Oryginalny odczyt DOM, identyfikatory elementów, walidacja decyzji i kontrola aktualności strony
  pochodzą z jev-ultrafast. To nie jest ogólny router modeli ani usługa Browser Use Cloud.

## Instalacja (PowerShell)

Wymagane: [uv](https://docs.astral.sh/uv/) oraz Python 3.12+ (uv może go pobrać).

```powershell
cd C:\Users\User\Documents\GitHub\JevUltrafastMCP
uv sync --locked --python 3.12
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD/.browsers"
uv run playwright install chromium
```

W hoście MCP (np. AgentDashboard) skonfiguruj zmienne środowiskowe procesu serwera.
Klucze ustaw w przeznaczonych do tego polach sekretów hosta:

```dotenv
TYPESAFE_API_KEY=twoj_klucz_typesafe
OPENAI_API_KEY=twoj_klucz_openai
TYPESAFE_MODEL=jev-latest
OPENAI_MODEL=gpt-6-luna
```

Serwer korzysta wyłącznie ze zmiennych środowiskowych przekazanych przez hosta;
nie odczytuje samodzielnie żadnego pliku `.env`. `.env.example` jest jedynie listą
zmiennych do skonfigurowania w hoście. Istniejący lokalny `.env` nie jest używany.
Brak `TYPESAFE_API_KEY` zatrzymuje wywołanie `browse` z komunikatem wskazującym nazwę zmiennej.
Klucz OpenAI jest potrzebny tylko przy wpisywaniu tekstu; jego brak również daje
czytelny błąd `OPENAI_API_KEY`, bez wpisywania danych i bez ujawniania sekretów.
Konto OpenAI musi mieć dostęp do modelu `gpt-6-luna`. Nie wpisuj kluczy w argumentach narzędzia.
Katalog `.browsers` jest wykrywany automatycznie; `PLAYWRIGHT_BROWSERS_PATH` może go nadpisać.
Na Linuksie można użyć `uv run playwright install --with-deps chromium`.

## Konfiguracja klienta MCP

Po instalacji najprościej uruchamiać bezpośrednio interpreter środowiska:

```json
{
  "mcpServers": {
    "jev-ultrafast": {
      "command": "C:/Users/User/Documents/GitHub/JevUltrafastMCP/.venv/Scripts/python.exe",
      "args": ["-m", "jev_ultrafast_mcp.server"]
    }
  }
}
```

Gotowy przykład: `mcp.example.json`. Dla klienta z konfiguracją TOML:

```toml
[mcp_servers.jev-ultrafast]
command = "C:/Users/User/Documents/GitHub/JevUltrafastMCP/.venv/Scripts/python.exe"
args = ["-m", "jev_ultrafast_mcp.server"]
env_vars = ["TYPESAFE_API_KEY", "OPENAI_API_KEY", "TYPESAFE_MODEL", "OPENAI_MODEL"]
```

W przykładzie TOML `env_vars` przekazuje zmienne dostępne w środowisku hosta.
Host musi je otrzymać przed uruchomieniem serwera. W AgentDashboard użyj konfiguracji
environment/secrets danego serwera; samo zapisanie kluczy w pliku na dysku nie wystarczy.

Alternatywnie: `uv run --directory C:/Users/User/Documents/GitHub/JevUltrafastMCP jev-ultrafast-mcp`.
To serwer `stdio`: oczekuje komunikatów MCP, nie otwiera strony ani konsoli interaktywnej.
Nie został automatycznie dopisany do konfiguracji żadnego klienta.

## Narzędzie `browse`

```json
{
  "url": "https://en.wikipedia.org/wiki/Main_Page",
  "goal": "Find and open the article about Gödel's incompleteness theorems.",
  "max_steps": 60,
  "timeout_seconds": 120
}
```

`url` i `goal` są wymagane. `max_steps`: 1–200, domyślnie 60.
`timeout_seconds`: 1–600, domyślnie 120. Budżet czasu obejmuje start przeglądarki,
jest sprawdzany między decyzjami i przed wprowadzeniem danych. Trwające wywołanie może
przekroczyć budżet: dostawcy mają timeout 25 s, TypeSafe ponawia odpowiedzi 429/503/529
maksymalnie dwa razy; start Chromium ma 30 s, początkowa nawigacja 15 s.
Niezależny watchdog kończy własne drzewo procesów Chromium po upływie budżetu,
również przy zawieszonym rendererze. Anulowanie wywołania MCP czeka na zakończenie
trwającego zapytania i posprzątanie sesji.

Odpowiedź zawiera `status` (`done`, `blocked`, `step_limit`, `timeout`, `error`),
`url`, `title`, `text`, `history`, `decisions`, `text_calls`, `elapsed_ms`, `error`
oraz `verified: false`. Historia obejmuje wykonane działania, także gdy późniejsze
odczytanie strony nie powiodło się. Wtedy końcowy tekst może być ostatnią poprawną obserwacją.
`done` oznacza ocenę agenta; wynik trzeba niezależnie zweryfikować na podstawie strony.

Przeglądarka zamyka się po każdym wywołaniu, także po błędzie. Cookies i logowanie
nie przechodzą do następnego zadania. Treść stron i wprowadzane wartości trafiają
do odpowiednich dostawców modeli; wyniki i historia mogą zawierać dane ze strony.
Serwer nie zapisuje zrzutów ekranu ani śladów zadań na dysku.

## Ograniczenia

Jak oryginalny eksperyment: brak obsługi iframe, shadow DOM, canvas, uploadów,
nowych kart, zagnieżdżonego przewijania i dowolnych skrótów klawiaturowych.
Obsługiwane operacje to CLICK, TYPE_TEXT, SELECT, SCROLL_UP/DOWN, WAIT, DONE, BLOCKED.
Model wybiera wyłącznie zaobserwowane elementy; nie wykonujemy wygenerowanego kodu ani selektorów.
Narzędzie może wysyłać formularze i wykonywać działania na witrynach. Udostępniaj je
zaufanemu klientowi lokalnemu; nie jest sandboxem sieciowym ani filtrem adresów intranetu.

## Weryfikacja

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD/.browsers"
uv run pytest -q
uv run ruff check .
uv build
```

Testy uruchamiają rzeczywisty Chromium na lokalnej stronie, sprawdzają wpisywanie,
klikanie, odrzucanie nieaktualnych decyzji, izolację sesji, limity, sprzątanie oraz
komunikację MCP przez stdio. Odpowiedzi dostawców są zastępcze: testy nie zużywają
płatnych API i nie potwierdzają dostępu konta do modeli.

Pochodzenie kodu i przypięty revision upstream: `THIRD_PARTY.md`; licencja: `LICENSE.upstream`.
