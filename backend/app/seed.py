from sqlalchemy import func, select
from .db.session import AsyncSessionLocal
from .models.inbox_message import InboxMessage
from .models.plugin import Plugin
from .models.routing_rule import RoutingRule
from .models.user import User
from .services.user_service import create_user


def _sample_workspace(name: str, description: str, category: str):
    return {
        'id': f'workspace_{name.lower().replace(" ", "_")}',
        'name': name,
        'description': description,
        'requires': 'numpy, httpx',
        'updatedAt': '2026-03-20T12:00:00Z',
        'stats': {'nodes': 4, 'edges': 3, 'folders': 0},
        'graph': {
            'nodes': [
                {'id': 'node_1', 'label': f'{name} Start', 'category': 'text', 'inputs': [], 'outputs': ['text'], 'code': 'res = "hello"', 'x': 0, 'y': 0},
                {'id': 'node_2', 'label': 'HTTP', 'category': 'http-request', 'inputs': ['url'], 'outputs': ['response'], 'x': 240, 'y': 0},
                {'id': 'node_3', 'label': 'Classifier', 'category': 'agent-task' if category == 'llm' else 'url-parse', 'inputs': ['input'], 'outputs': ['result'], 'x': 480, 'y': 0},
                {'id': 'node_4', 'label': 'Output', 'category': 'print', 'inputs': ['value'], 'outputs': ['value'], 'x': 720, 'y': 0}
            ],
            'edges': [
                {'id': 'edge_1', 'from': {'nodeId': 'node_1', 'type': 'out', 'portIndex': 0}, 'to': {'nodeId': 'node_2', 'type': 'in', 'portIndex': 0}},
                {'id': 'edge_2', 'from': {'nodeId': 'node_2', 'type': 'out', 'portIndex': 0}, 'to': {'nodeId': 'node_3', 'type': 'in', 'portIndex': 0}},
                {'id': 'edge_3', 'from': {'nodeId': 'node_3', 'type': 'out', 'portIndex': 0}, 'to': {'nodeId': 'node_4', 'type': 'in', 'portIndex': 0}}
            ],
            'folders': [],
            'envVars': []
        }
    }


async def seed_initial_data():
    async with AsyncSessionLocal() as session:
        user_count = await session.scalar(select(func.count(User.id)))
        if not user_count:
            await create_user(session, 'demo@tokenflow.local', 'demo123456')

        plugin_count = await session.scalar(select(func.count(Plugin.id)))
        if not plugin_count:
            session.add_all([
                Plugin(
                    name='Knowledge Base Builder',
                    slug='knowledge-base-builder',
                    summary='PDF parsing, chunking and vector indexing workflow template.',
                    category='knowledge',
                    plugin_type='workflow',
                    author_name='TokenFlow Team',
                    tags=['knowledge', 'pdf', 'embedding'],
                    source={'version': '1.0.0', 'channel': 'community'},
                    workspace_snapshot=_sample_workspace('Knowledge Builder', 'Build a searchable PDF knowledge base.', 'knowledge'),
                    is_public=True,
                    installs=12,
                    downloads=18
                ),
                Plugin(
                    name='Routing Copilot',
                    slug='routing-copilot',
                    summary='Rule and AI assisted message routing template.',
                    category='routing',
                    plugin_type='module',
                    author_name='TokenFlow Team',
                    tags=['routing', 'classifier', 'ops'],
                    source={'version': '1.1.0', 'channel': 'official'},
                    workspace_snapshot=_sample_workspace('Routing Copilot', 'Classify incoming requests and route them.', 'llm'),
                    is_public=True,
                    installs=8,
                    downloads=11
                ),
                Plugin(
                    name='URL Insight Toolchain',
                    slug='url-insight-toolchain',
                    summary='Parse URLs and summarize fetched results.',
                    category='tools',
                    plugin_type='workflow',
                    author_name='Community Builder',
                    tags=['tools', 'http', 'url'],
                    source={'version': '0.9.2', 'channel': 'community'},
                    workspace_snapshot=_sample_workspace('URL Insight', 'Inspect and classify URL data.', 'tools'),
                    is_public=True,
                    installs=5,
                    downloads=7
                )
            ])

        rule_count = await session.scalar(select(func.count(RoutingRule.id)))
        if not rule_count:
            session.add_all([
                RoutingRule(
                    name='Billing Email Escalation',
                    category='billing',
                    channel='email',
                    matcher_type='keyword',
                    matcher_config={'keywords': ['invoice', 'billing', 'refund', 'payment failed']},
                    action_config={'target': 'finance-team', 'priority': 'high'},
                    classifier_mode='rule',
                    priority=10,
                    enabled=True,
                    is_public=True
                ),
                RoutingRule(
                    name='Plugin Review Queue',
                    category='marketplace',
                    channel='community',
                    matcher_type='keyword',
                    matcher_config={'keywords': ['plugin', 'publish', 'review', 'market']},
                    action_config={'target': 'plugin-review', 'priority': 'medium'},
                    classifier_mode='rule',
                    priority=20,
                    enabled=True,
                    is_public=True
                ),
                RoutingRule(
                    name='Knowledge Ingestion Requests',
                    category='knowledge',
                    channel='api',
                    matcher_type='keyword',
                    matcher_config={'keywords': ['pdf', 'chunk', 'embedding', 'index']},
                    action_config={'target': 'knowledge-pipeline', 'priority': 'high'},
                    classifier_mode='rule',
                    priority=15,
                    enabled=True,
                    is_public=True
                )
            ])

        message_count = await session.scalar(select(func.count(InboxMessage.id)))
        if not message_count:
            session.add_all([
                InboxMessage(title='Marketplace sync ready', body='Community marketplace has three starter modules ready for import.', category='marketplace', channel='dashboard', extra={'level': 'info'}),
                InboxMessage(title='Routing rules updated', body='Billing and plugin review channels are now covered by public rules.', category='routing', channel='dashboard', extra={'level': 'success'}),
                InboxMessage(title='Cloud file storage online', body='Authenticated users can now store workspace snapshots in PostgreSQL.', category='workspace', channel='dashboard', extra={'level': 'warning'})
            ])

        await session.commit()
