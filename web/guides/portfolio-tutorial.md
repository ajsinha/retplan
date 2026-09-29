# From a broker export to a ten-year projection

A tutorial: turn the positions export your broker gives you into a portfolio of accounts
priced every day, add the rest of what you own and owe, check it, project it, stress it -
and link your plan to it.

## 1. Export your positions

Every broker has a download of current positions - usually called *Positions*,
*Holdings* or *Portfolio*, as Excel or CSV. You need nothing else: RetPlan finds the table
inside it.

## 2. Build the portfolio

Open **Portfolios → From a multi-account file**, choose the file and press **Analyse**.
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
no account go to one called *Brokerage*.

Choose **A new portfolio**, name it, and import. Each account in the file becomes an
account of the portfolio. Prices arrive within seconds and then every day.

A file for one account only? Create the portfolio, **Add account**, pick its type, and on
the account's page use **Upload positions** - every line goes into that account.

!!! warning "Pence and pounds"
    London prices are quoted in pence. If your file gives prices in pounds and a line is
    flagged as "about 100× Yahoo's", the match is right and the file's unit differs.

## 3. Add the rest, and check it

A portfolio is more than investments. **Add account** for your bank balances (checking,
savings, CDs), your home and other property, and your debts - a mortgage, a car loan, a
credit card. Cash and property are values you update now and then; a debt pays itself
down month by month from its rate and payment.

The portfolio page shows net worth, investable assets (investments plus cash) with today's
change, property, debts and the past year, then your accounts grouped by kind, a year of
value, and the allocation by asset class, tax treatment, account and owner. **Portfolio
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
the quick start, with its accounts taken from the portfolio, asking only what you save
into each - or **Link** the active plan to it. A linked plan takes every account and debt
from the portfolio each time it runs: balances, cost basis, what each account holds, and a
tax wrapper that follows the account's type. What the plan adds - contributions, employer
match, draw order - is kept. The plan's projection then always starts from what you
actually own and owe.
