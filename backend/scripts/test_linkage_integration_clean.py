"""
3.4- - 

?
1. 
2. 
3. 
4. ?
5. 
6. 
7.  (?
"""

import requests
import sys
from datetime import datetime

# 
BASE_URL = "http://127.0.0.1:8000"
API_BASE = f"{BASE_URL}/api/v1"

# 
TEST_ORG_ID = 1
TEST_USER_ID = 1  #  admin 


def test_linkage_plan_crud():
    """ CRUD """
    print("\n=== Test 1:  ===")
    
    # 
    plan_data = {
        "plan_name": f"_{datetime.now().strftime('%H%M%S')}",
        "org_id": TEST_ORG_ID,
        "fire_type": "building_fire",
        "trigger_alarm_type": "fire",
        "actions": [
            {
                "action_type": "start_exhaust",
                "target_device_id": None,
                "params": {"fan_id": 999}
            },
            {
                "action_type": "close_door",
                "target_device_id": None,
                "params": {}
            }
        ],
        "is_enabled": True
    }
    
    response = requests.post(
        f"{API_BASE}/linkage-plans",
        json=plan_data
    )
    
    if response.status_code != 200:
        print(f"?FAILED: Create status={response.status_code}")
        return None
    
    plan = response.json()["data"]
    print(f"?PASSED: Created plan with id={plan['id']}")
    return plan


def test_get_plans(plan):
    """"""
    print(f"\n=== Test 2:  (id={plan['id']}) ===")
    
    response = requests.get(
        f"{API_BASE}/linkage-plans?page=1&page_size=100",
        params={"org_id": plan["org_id"]}
    )
    
    if response.status_code != 200:
        print(f"?FAILED: Get list status={response.status_code}")
        return False
    
    data = response.json()
    items = data.get("data", {}).get("items", [])
    
    found = any(p["id"] == plan["id"] for p in items)
    
    if found:
        print(f"?PASSED: Found {len(items)} plans including the new one")
        return True
    else:
        print(f"?FAILED: Plan not found in list")
        return False


def test_update_plan(plan):
    """"""
    print(f"\n=== Test 3:  (id={plan['id']}) ===")
    
    update_data = {
        "plan_name": f"_{datetime.now().strftime('%H%M%S')}",
        "fire_type": "pre_fire",
        "trigger_alarm_type": "pre_fire",
        "actions": plan["actions"] + [
            {
                "action_type": "broadcast",
                "target_device_id": None,
                "params": {}
            }
        ],
        "is_enabled": plan["is_enabled"]
    }
    
    response = requests.put(
        f"{API_BASE}/linkage-plans/{plan['id']}",
        json=update_data
    )
    
    if response.status_code != 200:
        print(f"?FAILED: Update status={response.status_code}")
        return False
    
    updated = response.json()["data"]
    
    if updated["plan_name"] == update_data["plan_name"]:
        print(f"?PASSED: Updated to '{updated['plan_name']}'")
        return True
    else:
        print(f"?FAILED: Name not updated correctly")
        return False


def test_toggle_status(plan):
    """/?""
    print(f"\n=== Test 4: ?(id={plan['id']}) ===")
    
    # ?opposite
    new_status = not plan["is_enabled"]
    
    response = requests.post(
        f"{API_BASE}/linkage-plans/{plan['id']}/toggle"
    )
    
    if response.status_code != 200:
        print(f"?FAILED: Toggle status={response.status_code}")
        return False
    
    toggled = response.json()["data"]
    
    if toggled["is_enabled"] != new_status:
        print(f"?FAILED: Status should be {new_status}, got {toggled['is_enabled']}")
        return False
    
    print(f"?PASSED: Status changed from {plan['is_enabled']} to {toggled['is_enabled']}")
    return True


def test_simulate_trigger(plan):
    """"""
    print(f"\n=== Test 5:  (id={plan['id']}) ===")
    
    response = requests.post(
        f"{API_BASE}/linkage-plans/{plan['id']}/simulate"
    )
    
    if response.status_code != 200:
        print(f"?FAILED: Simulate status={response.status_code}")
        return False
    
    result = response.json()
    
    if result.get("code") == 200:
        logs = result.get("data", {})
        total = len(logs.get("logs", []))
        
        if total > 0:
            print(f"?PASSED: Generated {total} linkage log(s)")
            
            # ?
            log = logs["logs"][0]
            print(f"   - Log ID: {log['id']}")
            print(f"   - Action Type: {log['action_type']}")
            print(f"   - Status: {log['status']}")
            print(f"   - Result: {log.get('result_message', 'N/A')}")
            
            return True
        else:
            print(f"?FAILED: No logs generated")
            return False
    else:
        print(f"?FAILED: {result.get('message', 'Unknown error')}")
        return False


def test_query_logs(plan):
    """"""
    print(f"\n=== Test 6:  (plan_id={plan['id']}) ===")
    
    response = requests.get(
        f"{API_BASE}/alarm-linkage-logs?plan_id={plan['id']}"
    )
    
    if response.status_code != 200:
        print(f"?FAILED: Query logs status={response.status_code}")
        return False
    
    result = response.json()
    total = len(result.get("data", {}).get("logs", []))
    
    if total >= 2:  # ?2 start_exhaust + close_door?
        print(f"?PASSED: Found {total} linkage logs")
        return True
    else:
        print(f"?FAILED: Expected at least 2 logs, got {total}")
        return False


def test_delete_protection():
    """"""
    print(f"\n=== Test 7:  (? ===")
    
    # ?
    # ?
    pass


def test_manual_execution(plan):
    """"""
    print(f"\n=== Test 8:  (id={plan['id']}) ===")
    
    execute_data = {
        "plan_id": plan["id"],
        "operator_id": 1,
        "operator_name": "test_operator"
    }
    
    response = requests.post(
        f"{API_BASE}/linkage-plans/execute",
        json=execute_data
    )
    
    if response.status_code != 200:
        print(f"?FAILED: Execute status={response.status_code}")
        return False
    
    result = response.json()
    
    if result.get("code") == 200:
        logs = result.get("data", {})
        total = len(logs.get("logs", []))
        
        if total > 0:
            print(f"?PASSED: Manual execution generated {total} log(s)")
            return True
        else:
            print(f"?FAILED: No logs generated")
            return False
    else:
        print(f"?FAILED: {result.get('message', 'Unknown error')}")
        return False


def main():
    """Main test workflow"""
    print("=" * 80)
    print("3.4-Linkage Function - Core Integration Test")
    print("=" * 80)
    
    results = []
    
    # Step 1: Create plan
    plan = test_linkage_plan_crud()
    results.append(("Create Plan", plan is not None))
    
    if not plan:
        print("\n[!] Core test failed - cannot continue")
        print_results(results)
        return 1
    
    # Step 2: Query plans
    results.append(("Query Plans", test_get_plans(plan)))
    
    # Step 3: Update plan
    results.append(("Update Plan", test_update_plan(plan)))
    
    # Step 4: Toggle status
    results.append(("Toggle Status", test_toggle_status(plan)))
    
    # Step 5: Simulate trigger
    results.append(("Simulate Trigger", test_simulate_trigger(plan)))
    
    # Step 6: Query logs
    results.append(("Query Logs", test_query_logs(plan)))
    
    # Step 8: Manual execution
    results.append(("Manual Execution", test_manual_execution(plan)))
    
    print("\n" + "=" * 80)
    print_results(results)
    
    all_passed = all(success for _, success in results)
    
    if all_passed:
        print("\n[SUCCESS] ALL TESTS PASSED!")
        return 0
    else:
        failed = sum(1 for _, s in results if not s)
        print(f"\n[WARNING] {failed} out of {len(results)} tests failed")
        return 1


def print_results(results):
    """"""
    passed = sum(1 for _, s in results if s)
    total = len(results)
    
    print(f"\npassed}/{total} ")
    print("-" * 80)
    
    for name, success in results:
        status = "?PASSED" if success else "?FAILED"
        print(f"{name:30s} {status}")


if __name__ == "__main__":
    exit(main())

