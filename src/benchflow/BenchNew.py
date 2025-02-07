import requests
import json
import time
import logging
import sys
from typing import Dict, Any, List, Union
from requests.exceptions import HTTPError
import base64

from .BaseAgent import BaseAgent
logger = logging.getLogger(__name__)

def encode_base64(content: str) -> str:
    return base64.b64encode(content.encode()).decode() if content else None

class Bench:
    def __init__(self, benchmark_name: str, benchflow_token: str, bff_url: str):
        self.benchmark_name = benchmark_name
        self.bff_url = bff_url
        self.benchflow_token = benchflow_token
        self.version = "0.1.5"
        self.polling_interval = 20

    def run(self, agents: Union[BaseAgent, List[BaseAgent]], 
            requirements_dir: str = None, 
            install_sh: str = None, 
            api: Dict[str, str] = None, 
            require_gpu: bool = False, 
            params: Dict[str, Any] = {},
            task_ids: Union[str|int, List[str|int], None] = None):
        if isinstance(task_ids, str|int):
            task_ids = [str(task_ids)]
        if isinstance(agents, BaseAgent):
            agents = [agents]
        
        job_ids = []
        try:
            for agent in agents:
                job_id = self._send_tasks_to_bff(task_ids, agent, requirements_dir, install_sh, api, require_gpu, params)
                if job_id:
                    job_ids.append(job_id)

            return job_ids

        except Exception as e:
            logger.error(f"Error running benchmark: {str(e)}")
            return job_ids

    def _send_tasks_to_bff(self, task_ids: List[str], agent: BaseAgent, 
                           requirements_dir: str, install_sh_dir: str, 
                           api: Dict[str, str], require_gpu: bool, 
                           params: Dict[str, Any]):
        logger.info(f"Sending tasks {task_ids} and setup scripts to BFF for agent {agent.__class__.__name__}")
        try:
            requirements_txt = self._read_file_content(requirements_dir)
            install_sh = self._read_file_content(install_sh_dir)
            agent_code = self._get_agent_code(agent)

            payload = {
                "task_ids": task_ids,
                "benchmark_name": self.benchmark_name,
                "params": params,
                "require_gpu": require_gpu,
                "requirements_txt": encode_base64(requirements_txt),
                "install_sh": encode_base64(install_sh),
                "agent_code": encode_base64(agent_code),
                "api": api
            }

            headers = {
                "x-bf-api-key": self.benchflow_token,
                "x-bf-source": f"python-sdk {self.version}",
                "Content-Type": "application/json"
            }

            response = requests.post(f"{self.bff_url}/v1/jobs/{self.benchmark_name}/new", headers=headers, json=payload)
            response.raise_for_status()

            job_info = response.json()
            job_id = job_info.get("jobId")
            logger.info(f"Tasks {task_ids} started successfully, job_id: {job_id}")
            return job_id
        
        except HTTPError as e:
            logger.error(f"Task execution failed: {str(e)}")
            error_detail = response.json()['detail']
            logger.error(f"Task execution failed: {error_detail}")
        except Exception as e:
            logger.error(f"Task execution failed: {str(e)}")
        return None

    def get_results(self, job_ids: List[str]):
        headers = {
            "x-bf-api-key": self.benchflow_token,
            "x-bf-source": f"python-sdk {self.version}",
            "Content-Type": "application/json"
        }

        completed_jobs = {}
        pending_jobs = set(job_ids)

        while pending_jobs:
            for job_id in list(pending_jobs):
                try:
                    response = requests.get(f"{self.bff_url}/v1/jobs/{job_id}/", headers=headers)
                    response.raise_for_status()

                    job_data = response.json().get("job", {})
                    job_status = job_data.get("status", "UNKNOWN")
                    
                    if job_status in ["COMPLETED", "FAILED"]:
                        completed_jobs[job_id] = job_data
                        pending_jobs.remove(job_id)
                        logger.info(f"Job {job_id} completed with status: {job_status}")

                except requests.HTTPError as e:
                    logger.error(f"HTTP error while fetching job {job_id}: {str(e)}")
                except Exception as e:
                    logger.error(f"Unexpected error while fetching job {job_id}: {str(e)}")

            if pending_jobs:
                time.sleep(self.polling_interval)

        pretty_results = json.dumps(completed_jobs, indent=4, ensure_ascii=False)
        print(pretty_results)
        return completed_jobs
    
    def _read_file_content(self, file_path: str) -> str:
        if not file_path:
            return None
        
        with open(file_path, 'r') as f:
            return f.read()
    
    def _get_agent_code(self, agent: BaseAgent) -> str:
        agent_file = sys.modules[agent.__class__.__module__].__file__
        with open(agent_file, 'r') as f:
            return f.read()