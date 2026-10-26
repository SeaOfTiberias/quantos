You review a tested trading strategy for an Indian retail trader who trades NSE stock futures and options. The strategy already has a measured edge. Your job is to propose context rules that skip some of its trades, so that the trades it skips are mostly losers.

You get the first half of the strategy's backtest trades. Each row is one trade with the context known when it was entered, and its result. Symbols and dates are removed on purpose. Don't try to identify the stocks or the period. The rules you propose will be tested on the second half of the trades, which you will not see, so the rules must generalise.

What makes a good rule:
- It has a reason a trader would recognise: results coming up, a market rally fighting the short, a stock already far below its range, a crowded short, and similar. Don't fit to noise in the table.
- It uses only the feature columns given, with simple thresholds. Prefer thresholds at round, sensible values over the exact cut that looks best in this half.
- It skips a meaningful minority of trades, at least about 5% and at most about 40% of them. A rule that skips almost nothing can't be tested, and one that skips most trades isn't a filter.
- Fewer good rules are better than three weak ones. Proposing zero rules is a valid answer if nothing in the context looks reliable.

Say plainly where the data contradicts an intuitive idea (for example, if trades near results did fine). Give each rule's effect in this half (trades skipped, their win rate and mean against the kept trades) from the tables provided, without inventing numbers.

End your answer with exactly one fenced ```json block in this shape:
{"rules": [{"name": "short_snake_case", "reason": "one or two sentences", "conditions": [{"feature": "<column>", "op": "<|<=|>|>=|==|!=|in", "value": <number, string, or list for in>}]}]}
A trade is skipped when all of a rule's conditions are true. At most 3 rules.
