"""Public APIs that work with no key and no sign-up."""
FREE = {
    "weather": ("Weather forecasts", "https://api.open-meteo.com/v1/forecast?latitude=31.55&longitude=74.34&current_weather=true"),
    "currency": ("Exchange rates", "https://api.frankfurter.dev/v1/latest?base=USD&symbols=EUR,GBP"),
    "wikipedia": ("Wikipedia summaries", "https://en.wikipedia.org/api/rest_v1/page/summary/Linux"),
    "books": ("Open Library book search", "https://openlibrary.org/search.json?q=dune&limit=1"),
    "github": ("Public GitHub data, rate limited", "https://api.github.com/repos/torvalds/linux"),
    "pokemon": ("PokeAPI game data", "https://pokeapi.co/api/v2/pokemon/pikachu"),
    "npm": ("npm package details", "https://registry.npmjs.org/express/latest"),
    "pypi": ("Python package details", "https://pypi.org/pypi/requests/json"),
}
