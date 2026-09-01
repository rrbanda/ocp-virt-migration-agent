"""Unit tests for OCP Virt / MTV integration tools."""

from unittest.mock import MagicMock, patch


class TestListVmwareVms:
    @patch("app.tools.ocp_tools.K8S_AVAILABLE", False)
    def test_returns_error_when_k8s_unavailable(self):
        from app.tools.ocp_tools import list_vmware_vms

        result = list_vmware_vms("test-ns")
        assert "error" in result
        assert "not installed" in result["error"]

    @patch("app.tools.ocp_tools.K8S_AVAILABLE", True)
    @patch("app.tools.ocp_tools._http_get")
    @patch("app.tools.ocp_tools._resolve_inventory", return_value=("https://inv.example.com", "token"))
    @patch("app.tools.ocp_tools.mtv_custom_api")
    @patch("app.tools.ocp_tools._k8s_list")
    def test_returns_vm_list(self, mock_list, mock_api, mock_inv, mock_http):
        mock_list.return_value = {
            "items": [
                {
                    "metadata": {"uid": "uid-1", "name": "vsphere-provider"},
                    "spec": {"type": "vsphere"},
                    "status": {"conditions": [{"type": "InventoryCreated", "status": "True"}]},
                }
            ]
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {
                "name": "test-vm-1",
                "id": "vm-1",
                "powerState": "poweredOn",
                "cpuCount": 4,
                "memoryMB": 8192,
                "guestName": "RHEL 8",
                "firmware": "bios",
                "disks": [{"capacity": 107374182400}],
                "networks": [{"id": "net-1", "name": "VM Network"}],
            }
        ]
        mock_http.return_value = mock_resp

        from app.tools.ocp_tools import list_vmware_vms

        result = list_vmware_vms("test-ns")
        assert result["vm_count"] == 1
        assert result["vms"][0]["name"] == "test-vm-1"
        assert result["vms"][0]["cpu_count"] == 4
        assert result["vms"][0]["total_disk_gb"] == 100.0

    @patch("app.tools.ocp_tools.K8S_AVAILABLE", True)
    @patch("app.tools.ocp_tools.mtv_custom_api")
    @patch("app.tools.ocp_tools._k8s_list")
    def test_no_vmware_provider(self, mock_list, mock_api):
        mock_list.return_value = {"items": [{"metadata": {"name": "ocp"}, "spec": {"type": "openshift"}}]}
        from app.tools.ocp_tools import list_vmware_vms

        result = list_vmware_vms("test-ns")
        assert "error" in result
        assert "No VMware provider" in result["error"]


class TestCreateMigrationPlan:
    @patch("app.tools.ocp_tools.K8S_AVAILABLE", True)
    def test_empty_namespace_returns_error(self):
        from app.tools.ocp_tools import create_migration_plan

        result = create_migration_plan(namespace="", vm_name="test-vm", plan_name="", target_namespace="", warm="false")
        assert "error" in result
        assert "namespace is required" in result["error"]

    @patch("app.tools.ocp_tools.K8S_AVAILABLE", True)
    def test_empty_vm_name_returns_error(self):
        from app.tools.ocp_tools import create_migration_plan

        result = create_migration_plan(namespace="ns", vm_name="", plan_name="", target_namespace="", warm="false")
        assert "error" in result
        assert "vm_name is required" in result["error"]

    @patch("app.tools.ocp_tools.K8S_AVAILABLE", False)
    def test_returns_error_when_k8s_unavailable(self):
        from app.tools.ocp_tools import create_migration_plan

        result = create_migration_plan(namespace="ns", vm_name="vm1", plan_name="", target_namespace="", warm="false")
        assert "error" in result

    @patch("app.tools.ocp_tools.K8S_AVAILABLE", True)
    @patch("app.tools.ocp_tools._http_get")
    @patch("app.tools.ocp_tools._resolve_inventory", return_value=("https://inv.example.com", "token"))
    @patch("app.tools.ocp_tools._k8s_get")
    @patch("app.tools.ocp_tools._k8s_create")
    @patch("app.tools.ocp_tools._k8s_list")
    @patch("app.tools.ocp_tools.mtv_custom_api")
    def test_creates_plan_crs(self, mock_api, mock_list, mock_create, mock_get, mock_inv, mock_http):
        mock_list.return_value = {
            "items": [
                {"metadata": {"uid": "uid-1", "name": "vsphere-prov"}, "spec": {"type": "vsphere"}},
                {"metadata": {"uid": "uid-2", "name": "ocp-prov"}, "spec": {"type": "openshift"}},
            ]
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = [
            {
                "name": "my-vm",
                "id": "vm-123",
                "cpuCount": 4,
                "memoryMB": 8192,
                "guestName": "RHEL 8",
                "firmware": "bios",
                "powerState": "poweredOff",
                "networks": [{"id": "net-1", "name": "VM Network"}],
                "disks": [{"capacity": 53687091200, "datastore": {"id": "ds-1"}}],
            }
        ]
        mock_http.return_value = mock_resp
        mock_get.return_value = {"status": {"conditions": [{"type": "Ready", "status": "True"}]}}

        from app.tools.ocp_tools import create_migration_plan

        result = create_migration_plan(namespace="ns", vm_name="my-vm", plan_name="", target_namespace="", warm="false")

        assert result["status"] == "plan_created"
        assert result["vm_name"] == "my-vm"
        assert result["plan_validation"] == "Ready"
        assert mock_create.call_count == 3  # NetworkMap, StorageMap, Plan (no Migration)

    @patch("app.tools.ocp_tools.K8S_AVAILABLE", True)
    @patch("app.tools.ocp_tools._http_get")
    @patch("app.tools.ocp_tools._resolve_inventory", return_value=("https://inv.example.com", "token"))
    @patch("app.tools.ocp_tools._k8s_list")
    @patch("app.tools.ocp_tools.mtv_custom_api")
    def test_vm_not_found_in_inventory(self, mock_api, mock_list, mock_inv, mock_http):
        mock_list.return_value = {
            "items": [
                {"metadata": {"uid": "uid-1", "name": "vsphere-prov"}, "spec": {"type": "vsphere"}},
                {"metadata": {"uid": "uid-2", "name": "ocp-prov"}, "spec": {"type": "openshift"}},
            ]
        }
        mock_resp = MagicMock()
        mock_resp.json.return_value = [{"name": "other-vm", "id": "vm-999"}]
        mock_http.return_value = mock_resp

        from app.tools.ocp_tools import create_migration_plan

        result = create_migration_plan(
            namespace="ns", vm_name="missing-vm", plan_name="", target_namespace="", warm="false"
        )
        assert "error" in result
        assert "not found" in result["error"]


class TestGetPodLogs:
    @patch("app.tools.ocp_tools.K8S_AVAILABLE", False)
    def test_returns_error_when_k8s_unavailable(self):
        from app.tools.ocp_tools import get_pod_logs

        result = get_pod_logs("ns", "forklift", 50)
        assert "error" in result

    @patch("app.tools.ocp_tools.K8S_AVAILABLE", True)
    @patch("app.tools.ocp_tools.mtv_core_api")
    def test_no_matching_pods(self, mock_core):
        mock_api = MagicMock()
        pods_resp = MagicMock()
        pods_resp.items = []
        mock_api.list_namespaced_pod.return_value = pods_resp
        mock_core.return_value = mock_api

        from app.tools.ocp_tools import get_pod_logs

        result = get_pod_logs("ns", "nonexistent-pattern", 50)
        assert "error" in result
        assert "No pods matching" in result["error"]
