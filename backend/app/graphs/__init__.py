"""LangGraph agentic workflows.

These sit *beside* the hand-rolled Agent A (services/agent.py), not on top of it.
LangGraph is used where its state machine + checkpointer + human-in-the-loop
`interrupt()` genuinely add value:

* risk_review  — human-in-the-loop approval gate for extracted risks.
* comparison   — multi-contract comparison agent (plan -> retrieve -> compare).
* obligation_calendar — normalizes obligations into a prioritized deadline calendar.

Every node calls the existing gateway (app.llm.gateway), so MOCK_LLM=1 keeps
working and we never fight the custom TCS endpoint.
"""
