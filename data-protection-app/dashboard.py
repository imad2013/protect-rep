"""
Dashboard - Simple web UI showing event counts from PostgreSQL

This displays the data protection dashboard that shows zero events
even though the processor is running and messages are being sent.
"""

from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
import psycopg2
from datetime import datetime, timedelta

# Configuration
DB_HOST = os.environ.get('DB_HOST', '127.0.0.1')
DB_PORT = int(os.environ.get('POSTGRES_HOST_PORT', os.environ.get('DB_PORT', '5432')))
DB_NAME = 'dataprotection'
DB_USER = 'dataprotection'
DB_PASS = 'dataprotection'

PORT = 8080

def get_event_stats():
    """Get event statistics from the database."""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            database=DB_NAME,
            user=DB_USER,
            password=DB_PASS
        )
        cur = conn.cursor()
        
        # Total events
        cur.execute("SELECT COUNT(*) FROM events")
        total_events = cur.fetchone()[0]
        
        # Events by type
        cur.execute("""
            SELECT event_type, COUNT(*) 
            FROM events 
            GROUP BY event_type 
            ORDER BY COUNT(*) DESC
        """)
        events_by_type = dict(cur.fetchall())
        
        # Events in last hour
        cur.execute("""
            SELECT COUNT(*) FROM events 
            WHERE timestamp > NOW() - INTERVAL '1 hour'
        """)
        last_hour = cur.fetchone()[0]
        
        # Recent events
        cur.execute("""
            SELECT id, event_type, user_id, timestamp 
            FROM events 
            ORDER BY timestamp DESC 
            LIMIT 10
        """)
        recent_events = [
            {'id': r[0], 'type': r[1], 'user_id': r[2], 'timestamp': str(r[3])}
            for r in cur.fetchall()
        ]
        
        cur.close()
        conn.close()
        
        return {
            'total_events': total_events,
            'events_last_hour': last_hour,
            'events_by_type': events_by_type,
            'recent_events': recent_events,
            'status': 'connected',
            'last_updated': datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            'total_events': 0,
            'events_last_hour': 0,
            'events_by_type': {},
            'recent_events': [],
            'status': f'error: {str(e)}',
            'last_updated': datetime.utcnow().isoformat()
        }

class DashboardHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/api/stats':
            stats = get_event_stats()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(stats, indent=2).encode())
            
        elif self.path == '/' or self.path == '/dashboard':
            stats = get_event_stats()
            
            html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Data Protection Dashboard</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #333; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin: 20px 0; }}
        .stat-card {{ background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .stat-value {{ font-size: 36px; font-weight: bold; color: #2196F3; }}
        .stat-label {{ color: #666; margin-top: 5px; }}
        .status-ok {{ color: #4CAF50; }}
        .status-error {{ color: #f44336; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #eee; }}
        th {{ background: #2196F3; color: white; }}
        .refresh-btn {{ background: #2196F3; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; }}
        .refresh-btn:hover {{ background: #1976D2; }}
        .alert {{ background: #fff3cd; border: 1px solid #ffc107; padding: 15px; border-radius: 4px; margin: 20px 0; }}
        .chart-container {{ background: white; padding: 20px; border-radius: 8px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🔒 Data Protection Dashboard</h1>
        <button class="refresh-btn" onclick="location.reload()">🔄 Refresh</button>
        
        <div style="margin: 20px 0;">
            Status: <span class="{'status-ok' if 'error' not in stats['status'] else 'status-error'}">{stats['status']}</span>
            | Last Updated: {stats['last_updated']}
        </div>
        
        {'<div class="alert">⚠️ WARNING: Dashboard shows zero events. Check event processor service.</div>' if stats['total_events'] == 0 else ''}
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{stats['total_events']}</div>
                <div class="stat-label">Total Events</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{stats['events_last_hour']}</div>
                <div class="stat-label">Events (Last Hour)</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{len(stats['events_by_type'])}</div>
                <div class="stat-label">Event Types</div>
            </div>
        </div>
        
        <div class="chart-container">
            <h2>Events by Type</h2>
            {self._generate_type_table(stats['events_by_type'])}
        </div>
        
        <div class="chart-container">
            <h2>Recent Events</h2>
            {self._generate_recent_events_table(stats['recent_events'])}
        </div>
    </div>
    
    <script>
        // Auto-refresh every 10 seconds
        setTimeout(() => location.reload(), 10000);
    </script>
</body>
</html>
            """
            
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(html.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
    
    def _generate_type_table(self, events_by_type):
        if not events_by_type:
            return "<p>No data available</p>"
        
        rows = ''.join([
            f"<tr><td>{etype}</td><td>{count}</td></tr>"
            for etype, count in events_by_type.items()
        ])
        
        return f"""
        <table>
            <tr><th>Event Type</th><th>Count</th></tr>
            {rows}
        </table>
        """
    
    def _generate_recent_events_table(self, events):
        if not events:
            return "<p>No events recorded</p>"
        
        rows = ''.join([
            f"<tr><td>{e['id']}</td><td>{e['type']}</td><td>{e['user_id']}</td><td>{e['timestamp']}</td></tr>"
            for e in events
        ])
        
        return f"""
        <table>
            <tr><th>ID</th><th>Type</th><th>User ID</th><th>Timestamp</th></tr>
            {rows}
        </table>
        """
    
    def log_message(self, format, *args):
        # Suppress default logging
        pass

def main():
    print(f"Starting Data Protection Dashboard on http://localhost:{PORT}")
    print("Press Ctrl+C to stop")
    
    server = HTTPServer(('localhost', PORT), DashboardHandler)
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down dashboard...")
        server.shutdown()

if __name__ == '__main__':
    main()
