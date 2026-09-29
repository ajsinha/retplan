# From a broker export to a ten-year projection

A tutorial: turn the positions export your broker gives you into accounts priced every
day, add the rest of what you own and owe, gather them into a portfolio, check it, project
it, stress it - and link your plan to it.

## 1. Export your positions

Every broker has a download of current positions - usually called *Positions*,
*Holdings* or *Portfolio*, as Excel or CSV. You need nothing else: RetPlan finds the table
inside it.

## 2. Import the file

Open **Portfolio → Import a file** (or **Import a file of several accounts** on the
Accounts page), choose the file and press **Analyse**.
RetPlan reads every sheet, recognises the columns, and identifies each security on Yahoo -
by symbol where there is one, else by ISIN, else by name. The review screen shows each
line with a confidence:

| Confidence | Means | What to do |
|---|---|---|
| certain | the symbol was found as written, or its ISIN matched | nothing |
| likely | found by name, or the file's price differs from Yahoo's a little | glance at the name |
| uncertain | the name match was weak, or the price differs a lot | pick another candidate or type the symbol |
| not found | nothing matched | type the symbol, or leave it unticked |

The file's accounts - an account column, or one sheet per account - are listed with a type
guessed from their names ("Roth", "401k", "Rollover", "IRA", "HSA", "SIPP", "Individual"...).
Check each type: it decides how the account is taxed in a retirement plan. Positions with
no account go to one called *Brokerage*. An account whose name matches one you already
have joins it rather than making a second.

Then choose where they go: **a new portfolio** of them (name it), **add them to a
portfolio** you already have, or **just the accounts**. Either way each account in the file
becomes one of your accounts - accounts are yours, not a portfolio's, and a portfolio is
only a selection of them. Prices arrive within seconds and then every day.

A file for one account only? On **Portfolio → Accounts**, **Add account**, pick its type,
and on the account's page use **Upload positions** - every line goes into that account.
**Paste** takes lines of symbol, quantity and, optionally, cost basis and asset class.

!!! warning "Pence and pounds"
    London prices are quoted in pence. If your file gives prices in pounds and a line is
    flagged as "about 100× Yahoo's", the match is right and the file's unit differs.

## 3. Add the rest, gather it, and check it

What you own is more than investments. On the Accounts page, **Add account** for your bank
balances (checking, savings, CDs), your home and other property, and your debts - a
mortgage, a car loan, a credit card. Each has its own currency. Cash and property are
values you update now and then; a debt pays itself down month by month from its rate and
payment. The Accounts page shows net worth over every account, each counted once, and
records it every day.

A **portfolio** is a selection: any of your accounts, and even other portfolios (a
*Household* portfolio made of *Mine* and *Partner's*, say). One account can be in as many
portfolios as you like, and a change to it - a trade, a new price, a balance - shows at
once in every portfolio that includes it. Make one with **Portfolio → Portfolios → New
portfolio** and tick the accounts; later, **Choose accounts** on its page changes the
selection. Taking an account out of a portfolio never deletes it.

The portfolio page shows net worth, investable assets (investments plus cash) with today's
change, property, debts and the past year, then its accounts grouped by kind (marked
*through* a part when they come from a portfolio it is made of), net worth over time, and
the allocation of the investable assets by asset class, tax treatment, account and
owner. **Portfolio
checks** flag single companies above 10% of the investable assets, large cash or crypto
shares, prices that are stale or missing, and holdings without a cost. Set a **target
mix** to see the trades that would restore it - including a version that only invests new
money, which avoids selling.

## 4. Project it

Press **Project**. Choose the years, yearly or quarterly rows, a return model, and add any
contributions or withdrawals. A **goal** in today's money adds the chance of reaching it.
The fan chart shows the middle 50% and 80% of futures; the table below gives every year or
quarter; three real futures - bad luck, middle and good luck - are shown year by year.

!!! note "Where the assumptions come from"
    A year of prices is enough to estimate volatility and correlation, and far too little
    to estimate an expected return. So returns start from long-run assumptions for each
    asset class, nudged toward a security's own long history when there is one. Every
    assumption is shown, and any can be overridden per holding.

## 5. Stress it

**Stress tests** replay 2008, the dot-com bust, Covid, the 2022 rate shock and the 1970s on
today's mix - how deep the fall, how long the recovery. On the projection page, **open every
trial with a crisis** to see what one in the first years would do to the odds.

## 6. Use it in the plan

The portfolio page's **Retirement plans using it** card offers **Start a plan from it** -
the quick start, with its accounts taken from the portfolio's accounts, asking only what
you save into each - or **Link** the active plan to it. A linked plan takes every account
and debt the portfolio includes each time it runs, and accounts joining or leaving the
portfolio join or leave the plan: balances, cost basis, what each account holds, and a
tax wrapper that follows the account's type. What the plan adds - contributions, employer
match, draw order - is kept. The plan's projection then always starts from what you
actually own and owe.
