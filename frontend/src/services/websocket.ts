import { useEffect, useRef, useCallback } from 'react';

interface WebSocketMessage {
  type: string;
  data: unknown;
}

export function useWebSocket(onMessage: (msg: WebSocketMessage) => void) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.hostname}:8000/ws`;
    
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[WS] Connected');
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as WebSocketMessage;
        onMessage(msg);
      } catch (e) {
        console.error('[WS] Parse error:', e);
      }
    };

    ws.onclose = () => {
      console.log('[WS] Disconnected, reconnecting in 3s...');
      reconnectTimeoutRef.current = setTimeout(connect, 3000);
    };

    ws.onerror = (error) => {
      console.error('[WS] Error:', error);
      ws.close();
    };
  }, [onMessage]);

  useEffect(() => {
    connect();
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) wsRef.current.close();
    };
  }, [connect]);

  const send = useCallback((msg: WebSocketMessage) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg));
    }
  }, []);

  return { send };
}