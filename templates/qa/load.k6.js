// k6 load test. Thresholds come from the spec's SLO / perf budget, never from "what the
// last run did": a threshold that fails turns the k6 exit code non-zero and fails CI.
//   k6 run -e SCENARIO=smoke -e BASE_URL=https://staging.example.com load.k6.js
// SCENARIO: smoke | load | stress | soak. Thresholds: https://grafana.com/docs/k6/latest/using-k6/thresholds/
// Scenarios/executors: https://grafana.com/docs/k6/latest/using-k6/scenarios/
import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:3000';
const P95_MS = Number(__ENV.P95_MS || 300);           // from the spec's SLO / perf budget
const ERROR_RATE = Number(__ENV.ERROR_RATE || 0.01);  // from the spec's error budget
const PEAK_VUS = Number(__ENV.PEAK_VUS || 50);        // from the declared scale tier

const SCENARIOS = {
  smoke: { executor: 'constant-vus', vus: 1, duration: '1m' },
  load: { executor: 'ramping-vus', stages: [
    { duration: '5m', target: PEAK_VUS }, { duration: '10m', target: PEAK_VUS }, { duration: '5m', target: 0 } ] },
  stress: { executor: 'ramping-vus', stages: [
    { duration: '5m', target: PEAK_VUS }, { duration: '5m', target: PEAK_VUS * 2 },
    { duration: '5m', target: PEAK_VUS * 3 }, { duration: '5m', target: 0 } ] },
  soak: { executor: 'constant-vus', vus: Math.ceil(PEAK_VUS * 0.8), duration: '2h' },
};
const name = __ENV.SCENARIO || 'smoke';

export const options = {
  scenarios: { [name]: SCENARIOS[name] },
  thresholds: {
    http_req_duration: [`p(95)<${P95_MS}`],
    http_req_failed: [{ threshold: `rate<${ERROR_RATE}`, abortOnFail: true, delayAbortEval: '30s' }],
  },
};

export default function () {
  const res = http.get(`${BASE_URL}/<critical read endpoint>`);
  check(res, { 'status is 200': (r) => r.status === 200 });
  sleep(1);
}
