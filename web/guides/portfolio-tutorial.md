# From a broker export to a ten-year projection

A tutorial: turn the positions export your broker gives you into a portfolio priced every
day, check it, project it, stress it - and use it in your plan.

## 1. Export your positions

Every broker has a download of current positions - usually called *Positions*,
*Holdings* or *Portfolio*, as Excel or CSV. You need nothing else: RetPlan finds the table
inside it.

## 2. Build the portfolio

Open **Portfolio → Build from a spreadsheet**, choose the file and press **Analyse**.
RetPlan reads every sheet, recognises the columns, and identifies each security on Yahoo -
by symbol where there is one, else by ISIN, else by name. The review screen shows each
line with a confidence:

| Confidence | Means | What to do |
|---|---|---|
| certain | the symbol was found as written, or its ISIN matched | nothing |
| likely | found by name, or the file's price differs from Yahoo's a little | glance at the name |
| uncertain | the name match was weak, or the price differs a lot | pick another candidate or type the symbol |
| not found | nothing matched | type the symbol, or leave it unticked |

Choose **A new portfolio**, name it, and **Import ticked holdings**. Prices arrive within
seconds and then every day.

!!! warning "Pence and pounds"
    London prices are quoted in pence. If your file gives prices in pounds and a line is
    flagged as "about 100× Yahoo's", the match is right and the file's unit differs.

## 3. Check it

The portfolio page shows value, today's change, gain on cost and a year of value, then
allocation by asset class and by account. **Portfolio checks** flag single companies
above 10% of the whole, large cash or crypto shares, prices that are stale or missing, and
holdings without a cost. Set a **target mix** to see the trades that would restore it -
including a version that only invests new money, which avoids selling.

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

At the foot of the portfolio page, **Use in your retirement plan** copies the value, cost
and mix into one of the plan's accounts. The plan's projection then starts from what you
actually hold.
