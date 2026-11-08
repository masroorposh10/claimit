# ClaimIt

**Find class-action settlements you actually qualify for, and get your claim ready in minutes.**

Billions of dollars in settlement money goes unclaimed every year because nobody reads the notices.
ClaimIt reads them for you. It pulls open settlements from public feeds, uses Claude to check each one
against a short profile of where you've lived and what you buy, and prepares a claim worksheet
for the ones you qualify for.

## Features

- **Automatic discovery**: pulls new open settlements from public RSS feeds
- **AI matching**: every notice is graded *likely / possible / unlikely* against your profile, with
  the reasons, payout, deadline, proof needed and official claim site pulled out
- **Claim worksheets**: an eligibility checklist, pre-filled answers and a list of proof to gather,
  with anything uncertain clearly marked `[CONFIRM: ...]`
- **Tracking**: mark claims drafted, filed or paid, and see how much you've actually received
- **Private by design**: your profile and database live only on your machine (both are git-ignored)

## Honest by design

Claim forms are signed under penalty of perjury. ClaimIt never invents purchases or details, only
calls something "likely" when your profile backs it up, and never submits anything for you.
You review and file every claim yourself on the official settlement site.

## Quick start

```bash
pip install -r requirements.txt
cp profile.example.json profile.json     # then fill in your real details
export ANTHROPIC_API_KEY=sk-ant-...      # or: ant auth login

python -m claimit fetch                  # pull open settlements
python -m claimit match 10               # check 10 against your profile
python -m claimit serve                  # dashboard at http://127.0.0.1:8000
```

Everything can also be done from the dashboard's buttons.

## Built with

Python, FastAPI, SQLite, and the Claude API (Claude Opus 5.5) using structured outputs.

## License

MIT. See [LICENSE](LICENSE).
