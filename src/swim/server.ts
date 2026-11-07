/**
 * SWIM-Compliant HTTP REST Server & Interactive Web Host
 */
import http from 'http';
import url from 'url';
import fs from 'fs';
import path from 'path';
import { AeroStore } from '../data/aero-store.js';
import { SwimFlightPlanService } from './swim-service.js';
import { SWIM_OPENAPI_SPEC } from './openapi.js';
import { AIRCRAFT_DATABASE } from '../performance/aircraft-database.js';
import { serializeToFixmXml, serializeToFixmJson } from '../ffice/fixm-serializer.js';
import { parseFixmXml, parseFixmJson } from '../ffice/fixm-deserializer.js';
import { validateFficeFlightPlan } from '../ffice/validator.js';

export function createSwimServer(service: SwimFlightPlanService, clientDir?: string): http.Server {
  const resolvedClientDir = clientDir || path.resolve(process.cwd(), 'src', 'client');

  const server = http.createServer(async (req, res) => {
    // Enable CORS for SWIM interop
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Accept, Authorization');

    if (req.method === 'OPTIONS') {
      res.writeHead(204);
      res.end();
      return;
    }

    const reqUrl = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);
    const pathname = reqUrl.pathname;
    const query = Object.fromEntries(reqUrl.searchParams.entries());
    const method = req.method?.toUpperCase() || 'GET';

    try {
      // 1. OpenAPI Specification & Documentation
      if (pathname === '/api/openapi.json' && method === 'GET') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(SWIM_OPENAPI_SPEC, null, 2));
        return;
      }

      if (pathname === '/api/docs' && method === 'GET') {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(`<!DOCTYPE html>
<html>
<head>
  <title>SWIM FF-ICE API Documentation</title>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css" />
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.onload = () => {
      window.ui = SwaggerUIBundle({
        url: '/api/openapi.json',
        dom_id: '#swagger-ui',
      });
    };
  </script>
</body>
</html>`);
        return;
      }

      // 2. Reference Data APIs
      if (pathname === '/api/v1/airports' && method === 'GET') {
        const queryStr = (query.query as string) || '';
        const limit = parseInt((query.limit as string) || '20', 10);
        const airports = service.getAeroStore().searchAirports(queryStr, limit);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(airports));
        return;
      }

      if (pathname === '/api/v1/waypoints' && method === 'GET') {
        const queryStr = (query.query as string) || '';
        const limit = parseInt((query.limit as string) || '30', 10);
        const waypoints = service.getAeroStore().searchWaypoints(queryStr, undefined, limit);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(waypoints));
        return;
      }

      if (pathname === '/api/v1/airspace/fir' && method === 'GET') {
        const firs = service.getAeroStore().getAllFirs();
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(firs));
        return;
      }

      if (pathname === '/api/v1/aircraft' && method === 'GET') {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(Object.values(AIRCRAFT_DATABASE)));
        return;
      }

      // 3. Trajectory Calculation & Sanity Advisory Service
      if (pathname === '/api/v1/trajectory/calculate' && method === 'POST') {
        const body = await readBody(req);
        const params = JSON.parse(body);
        const result = service.calculateTrajectory(params);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(result));
        return;
      }

      // 4. Plan Validation Service
      if (pathname === '/api/v1/ffice/validate' && method === 'POST') {
        const body = await readBody(req);
        let plan;
        if (body.trim().startsWith('<')) {
          plan = parseFixmXml(body);
        } else {
          plan = JSON.parse(body);
        }
        const report = validateFficeFlightPlan(plan);
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(report));
        return;
      }

      // 5. Flight Plan Filing / Submission
      if (pathname === '/api/v1/ffice/plans' && method === 'POST') {
        const body = await readBody(req);
        let planInput;
        const contentType = req.headers['content-type'] || '';
        if (contentType.includes('xml') || body.trim().startsWith('<')) {
          planInput = parseFixmXml(body);
        } else {
          planInput = JSON.parse(body);
        }

        const { plan, validation } = service.filePlan(planInput);

        const accept = req.headers['accept'] || '';
        if (accept.includes('xml') || accept.includes('vnd.fixm+xml')) {
          res.writeHead(201, { 'Content-Type': 'application/vnd.fixm+xml; charset=utf-8' });
          res.end(serializeToFixmXml(plan));
        } else {
          res.writeHead(201, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ plan, validation }));
        }
        return;
      }

      // 6. List Flight Plans
      if (pathname === '/api/v1/ffice/plans' && method === 'GET') {
        const plans = service.listPlans({
          callsign: query.callsign as string,
          departure: query.departure as string,
          arrival: query.arrival as string,
          status: query.status as string
        });
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(plans));
        return;
      }

      // 7. Get, Update, Cancel Plan by GUFI
      const gufiMatch = pathname.match(/^\/api\/v1\/ffice\/plans\/([a-zA-Z0-9-]+)$/);
      if (gufiMatch) {
        const gufi = gufiMatch[1];

        if (method === 'GET') {
          const plan = service.getPlan(gufi);
          if (!plan) {
            res.writeHead(404, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify({ error: `Flight plan with GUFI "${gufi}" not found.` }));
            return;
          }

          const accept = req.headers['accept'] || '';
          if (accept.includes('xml') || accept.includes('vnd.fixm+xml')) {
            res.writeHead(200, { 'Content-Type': 'application/vnd.fixm+xml; charset=utf-8' });
            res.end(serializeToFixmXml(plan));
          } else {
            res.writeHead(200, { 'Content-Type': 'application/json' });
            res.end(JSON.stringify(plan));
          }
          return;
        }

        if (method === 'PUT') {
          const body = await readBody(req);
          const updatedPlan = JSON.parse(body);
          const result = service.updatePlan(gufi, updatedPlan);
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify(result));
          return;
        }

        if (method === 'DELETE') {
          const cancelled = service.cancelPlan(gufi);
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify(cancelled));
          return;
        }
      }

      // 8. Serve Client UI static files
      let filePath = pathname === '/' ? 'index.html' : pathname.replace(/^\//, '');
      const fullFilePath = path.join(resolvedClientDir, filePath);

      if (fs.existsSync(fullFilePath) && fs.statSync(fullFilePath).isFile()) {
        const ext = path.extname(fullFilePath).toLowerCase();
        const mimeTypes: Record<string, string> = {
          '.html': 'text/html',
          '.js': 'application/javascript',
          '.css': 'text/css',
          '.json': 'application/json',
          '.png': 'image/png',
          '.svg': 'image/svg+xml'
        };
        const contentType = mimeTypes[ext] || 'application/octet-stream';
        res.writeHead(200, { 'Content-Type': contentType });
        fs.createReadStream(fullFilePath).pipe(res);
        return;
      }

      // Not found
      res.writeHead(404, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: `Endpoint "${pathname}" not found.` }));
    } catch (err: any) {
      res.writeHead(400, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: err.message || 'Internal server error' }));
    }
  });

  return server;
}

function readBody(req: http.IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let data = '';
    req.on('data', chunk => { data += chunk; });
    req.on('end', () => resolve(data));
    req.on('error', reject);
  });
}

// Standalone runner
if (process.argv[1] && process.argv[1].endsWith('server.ts')) {
  const store = new AeroStore();
  const service = new SwimFlightPlanService(store);
  const PORT = parseInt(process.env.PORT || '3000', 10);

  service.initialize().then(() => {
    const server = createSwimServer(service);
    server.listen(PORT, () => {
      console.log(`\n======================================================`);
      console.log(`✈️  SWIM FF-ICE Flight Plan Service is RUNNING`);
      console.log(`📡 Server Address: http://localhost:${PORT}`);
      console.log(`📖 OpenAPI Docs:   http://localhost:${PORT}/api/docs`);
      console.log(`💻 Web Interface:  http://localhost:${PORT}/`);
      console.log(`======================================================\n`);
    });
  });
}
