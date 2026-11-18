"""Live smoke test of Danube middleware APIs (no sales-offer generation).

Run from the repository root:
    python test_all_middleware_apis.py

Required environment variables (can be placed in .env):
    TEST_USER_ID, TEST_SALESFORCE_TOKEN, TEST_INVENTORY_TOKEN
    TEST_PROJECT_ID, TEST_OSF_PROJECT_ID, TEST_UNIT_ID
Optional for comparison: TEST_SECOND_UNIT_ID, TEST_SECOND_PROJECT_ID
Optional API keys: TEST_MARKETING_API_KEY, TEST_HOW_TO_VIDEOS_API_KEY,
                   TEST_OSF_PORTFOLIO_API_KEY

Does not log tokens, API keys, URLs or response bodies. Requests may be audited
or generate downloadable reports in upstream services. Run only in UAT.
"""
import asyncio
import os
import re
from dataclasses import dataclass
from urllib.parse import quote

from curl_cffi.requests import AsyncSession
from app.core.config import get_settings

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

SOURCE = 'Danube -one-chat'


def env(name):
    return (os.getenv(name) or '').strip()


def headers(extra=None):
    h = {'user_id': env('TEST_USER_ID'),
         'source': SOURCE,
         'salesforce_access_token': env('TEST_SALESFORCE_TOKEN')}
    h.update(extra or {})
    return h


@dataclass
class Check:
    name: str
    setting: str
    method: str
    required: tuple = ()
    api_key_env: str = ''
    path_var: str = ''
    body: object = None
    params: object = None
    inventory_bearer: bool = False
    timeout: int = 45


def build_checks(s):
    project = env('TEST_PROJECT_ID')
    osf = env('TEST_OSF_PROJECT_ID')
    unit = env('TEST_UNIT_ID')
    unit2 = env('TEST_SECOND_UNIT_ID')
    project2 = env('TEST_SECOND_PROJECT_ID') or project
    return [
        Check('Active Projects', 'inventory_project_api_url', 'GET', inventory_bearer=True),
        Check('Visible Units', 'inventory_units_api_url', 'GET', inventory_bearer=True),
        Check('Payment Plans', 'payment_plan_api_url', 'GET', ('TEST_UNIT_ID',), path_var='TEST_UNIT_ID'),
        Check('Project Information', 'project_information_api_url', 'GET', inventory_bearer=True),
        Check('Project Coordinates', 'project_coordinates_api_url', 'GET', ('TEST_PROJECT_ID',), path_var='TEST_PROJECT_ID'),
        Check('Unit Comparison', 'unit_comparison_api_url', 'POST', ('TEST_UNIT_ID','TEST_SECOND_UNIT_ID','TEST_PROJECT_ID'),
              body={'project_ids': f'{project},{project2}', 'unit_ids': f'{unit},{unit2}'}),
        Check('Unit Layout', 'unit_layout_api_url', 'GET', ('TEST_UNIT_ID',), path_var='TEST_UNIT_ID'),
        Check('Download Availability', 'availability_api_url', 'POST', ('TEST_PROJECT_ID',),
              body={'project_id': project, 'currency_code': env('TEST_CURRENCY') or 'AED',
                    'file_type': env('TEST_AVAILABILITY_FILE_TYPE') or 'pdf'}, timeout=60),
        Check('Bank Details', 'bank_details_api_url', 'POST', ('TEST_PROJECT_ID',), body={'projectId': project}),
        Check('Sales Offer - Unit Details', 'sales_offer_unit_details_url', 'POST', ('TEST_UNIT_ID',), body={'unitId': unit}),
        Check('Construction Update', 'construction_update_api_url', 'POST', ('TEST_OSF_PROJECT_ID',),
              params={'project_Id': osf}, timeout=60),
        Check('Marketing Content', 'marketing_api_url', 'POST', api_key_env='TEST_MARKETING_API_KEY', timeout=60),
        Check('How-to Videos', 'how_to_videos_api_url', 'POST', api_key_env='TEST_HOW_TO_VIDEOS_API_KEY'),
        Check('OSF Portfolio', 'osf_portfolio_api_url', 'GET', api_key_env='TEST_OSF_PORTFOLIO_API_KEY'),
    ]


async def run_one(session, s, check):
    missing = [x for x in ('TEST_USER_ID', 'TEST_SALESFORCE_TOKEN', *check.required) if not env(x)]
    if check.inventory_bearer and not env('TEST_INVENTORY_TOKEN'):
        missing.append('TEST_INVENTORY_TOKEN')
    if check.api_key_env and not env(check.api_key_env):
        missing.append(check.api_key_env)
    url = str(getattr(s, check.setting, '') or '').strip()
    if not url:
        missing.append(check.setting.upper())
    if missing:
        return 'SKIP', 'missing: ' + ', '.join(missing)
    if not url.startswith('https://'):
        return 'FAIL', 'API URL must use HTTPS'
    if check.path_var:
        url = url.rstrip('/') + '/' + quote(env(check.path_var), safe='')
    h = headers({'Accept': 'application/json'})
    if check.inventory_bearer:
        h['Authorization'] = 'Bearer ' + env('TEST_INVENTORY_TOKEN')
    if check.api_key_env:
        h['x_api_key'] = env(check.api_key_env)
    if check.name == 'Marketing Content':
        h['product_name'] = s.marketing_product_name
        h['product_feature_name'] = s.marketing_product_feature_name
    if check.method == 'POST' and check.body is not None:
        h['Content-Type'] = 'application/json'
    try:
        kwargs = dict(headers=h, timeout=check.timeout, allow_redirects=False)
        if check.params is not None:
            kwargs['params'] = check.params
        if check.body is not None:
            kwargs['json'] = check.body
        elif check.method == 'POST':
            kwargs['data'] = ''
        response = await session.request(check.method, url, **kwargs)
        code = response.status_code
        if code != 200:
            return 'FAIL', f'HTTP {code}'
        try:
            data = response.json()
        except ValueError:
            return 'FAIL', 'HTTP 200 but response is not JSON'
        if not isinstance(data, (dict, list)):
            return 'FAIL', 'Unexpected JSON root type'
        if isinstance(data, dict):
            metadata = data.get('metaData') or {}
            if isinstance(metadata, dict):
                status = str(metadata.get('status', '')).lower()
                status_code = str(metadata.get('statusCode', ''))
                if status and status not in ('success', 'successful'):
                    return 'FAIL', 'HTTP 200 but metaData.status is not SUCCESS'
                if status_code and status_code != '200':
                    return 'FAIL', 'HTTP 200 but metaData.statusCode is not 200'
            if data.get('success') is False:
                return 'FAIL', 'HTTP 200 but success=false'
        return 'PASS', 'HTTP 200; valid JSON; no reported metadata failure'
    except Exception as exc:
        # Do not print exception text: some libraries include request URLs/headers.
        return 'FAIL', 'transport exception: ' + type(exc).__name__


async def main():
    s = get_settings()
    print('Danube middleware live API smoke test (Currency excluded)')
    print('Headers: user_id, source, salesforce_access_token; x_api_key preserved')
    print('WARNING: This tests directly with supplied credentials, not the chatbot request pipeline.')
    print('WARNING: Download Availability may generate a report upstream.')
    results = []
    async with AsyncSession(impersonate='chrome') as session:
        for check in build_checks(s):
            status, reason = await run_one(session, s, check)
            results.append(status)
            print(f'{status:4} | {check.name:29} | {reason}')
    print('\nSummary:', ', '.join(f'{x}={results.count(x)}' for x in ('PASS','FAIL','SKIP')))
    print('Sales Offer generation deliberately omitted (side-effecting operation).')
    if 'FAIL' in results:
        raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
