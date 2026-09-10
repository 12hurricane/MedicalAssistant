"""Local inference plumbing.

Deliberately separate from ``app/agents`` and ``app/graph``, which are still empty
placeholders. This package is the transport and the prompt assembly — how a model is
reached and how untrusted text is fenced before it gets there. It is not an agent, and
importing it does not make anything in the application call a model.

Nothing in the request path imports this package yet. That is intentional: the
deterministic adherence and safety layers are the product, and a generative layer sits
on top of working medication data rather than replacing it.
"""
