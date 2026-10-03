"""Aggregate operations UI. No database driver, credentials or healthcare text."""
import os
from datetime import datetime, timedelta, timezone

import streamlit as st

from api_client import AnalyticsUnavailable, get_json

st.set_page_config(page_title='Healthcare Operations', page_icon='📊', layout='wide')
st.title('Healthcare Operations')
st.caption('Synthetic data only · Educational portfolio · Not HIPAA compliant')

base_url = os.environ.get('API_BASE_URL', 'http://127.0.0.1:8000')
today = datetime.now(timezone.utc).date()
st.sidebar.header('Filters')
all_time = st.sidebar.checkbox('All dates', value=True)
dates = st.sidebar.date_input('UTC date range', value=(today - timedelta(days=30), today), disabled=all_time)
category = st.sidebar.selectbox('Category', ['All', 'CLAIM_STATUS', 'MISSING_INFORMATION', 'BILLING_QUESTION', 'DOCUMENT_PROCESSING', 'OTHER'])
status = st.sidebar.selectbox('Workflow status', ['All', 'received', 'processed', 'failed'])
st.sidebar.button('Refresh')
st.sidebar.caption('Live API reads on each refresh. No database access from this dashboard.')
params = {}
if not all_time:
    if not isinstance(dates, tuple) or len(dates) != 2:
        st.info('Select both a start date and an end date.')
        st.stop()
    params.update(date_from=dates[0].isoformat(), date_to=dates[1].isoformat())
if category != 'All':
    params['category'] = category
if status != 'All':
    params['status'] = status

try:
    data = get_json(base_url, '/api/v1/analytics/summary', params)
    activity = get_json(base_url, '/api/v1/analytics/activity', {**params, 'limit': 30})
    readiness = get_json(base_url, '/ready')
except AnalyticsUnavailable:
    st.error('Operations data is unavailable. Check FastAPI and PostgreSQL, then refresh. No cached figures are shown.')
    st.stop()

try:
    st.success('API and PostgreSQL ready' if readiness['status'] == 'ready' else 'Readiness check incomplete')
    st.caption('Updated ' + datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))
    confidence = data['average_ai_confidence']
    values = [data['total_requests'], data['automated'], data['human_reviews'], data['failures'],
              f"{data['automation_rate']:.1f}%", 'N/A' if confidence is None else f'{confidence:.1%}']
    labels = ['TOTAL REQUESTS', 'AUTOMATED', 'HUMAN REVIEWS', 'FAILED', 'AUTOMATION RATE', 'AVG AI CONFIDENCE']
    for column, label, value in zip(st.columns(6), labels, values):
        column.metric(label, value)
    st.caption('Automated = AUTO_PROCESS without any human review. Rate = automated / total requests. Confidence excludes unclassified requests.')
    st.write(f"Completed: {data['completed_requests']} · Pending requests: {data['pending_requests']} · Pending reviews: {data['pending_reviews']}")
    for columns, specs in [(st.columns(2), [('Requests by Category', 'requests_by_category'), ('Workflow Decisions', 'requests_by_decision')]),
                           (st.columns(2), [('Processing Status', 'requests_by_status'), ('Agent Tool Usage', 'agent_tool_usage')])]:
        for column, (title, key) in zip(columns, specs):
            with column:
                st.subheader(title)
                st.bar_chart([{'label': label, 'count': count} for label, count in data[key].items()], x='label', y='count')
    st.write(f"Agent executions: {data['agent_executions']} · Failed agent runs: {data['agent_failures']} · Executed tools: {data['agent_tool_calls']} · Rejected calls: {data['agent_tool_rejections']} · AI failures: {data['ai_failures']}")
    st.subheader('Recent Activity')
    st.caption('Request metrics use creation dates; activity and agent metrics use event dates. Category/status filters exclude agent runs with no linked request.')
    # Fixed columns only: never display a generic upstream response/metadata blob.
    columns = ['created_at', 'event_type', 'actor', 'correlation_id', 'run_uuid']
    rows = [{key: item.get(key) for key in columns} for item in activity['items']]
    if rows:
        st.dataframe(rows, hide_index=True, width='stretch')
    else:
        st.info('No workflow activity matches these filters.')
except (KeyError, TypeError, ValueError):
    st.error('The analytics response is incompatible with this dashboard. Rebuild both services.')
