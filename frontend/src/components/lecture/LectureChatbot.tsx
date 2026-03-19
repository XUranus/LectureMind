import { useState, useRef, useEffect } from 'react';
import { Button, Spin, Tag, Tooltip } from 'antd';
import {
  SendOutlined,
  LoadingOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  BulbOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { API_PREFIX } from '../../config';
import { ChatMessageData, Citation } from '../../model';

// Helper: format seconds to mm:ss
const formatTime = (seconds: number): string => {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
};

// Citation badge component
interface CitationBadgeProps {
  citation: Citation;
  onTimeClick: (time: number) => void;
}

const CitationBadge: React.FC<CitationBadgeProps> = ({ citation, onTimeClick }) => {
  const icon = citation.type === 'knowledge_point'
    ? <BulbOutlined className="mr-1" />
    : <FileTextOutlined className="mr-1" />;

  return (
    <Tooltip
      title={`${citation.title} (${formatTime(citation.begin_time)} - ${formatTime(citation.end_time)})`}
    >
      <Tag
        className="cursor-pointer m-0.5"
        color={citation.type === 'knowledge_point' ? 'blue' : 'cyan'}
        onClick={() => onTimeClick(citation.begin_time)}
      >
        {icon}
        <ClockCircleOutlined className="mr-1" />
        {formatTime(citation.begin_time)}
        <span className="ml-1 text-xs opacity-75">[Source {citation.source_num}]</span>
      </Tag>
    </Tooltip>
  );
};


interface LectureChatBotProps {
  videoId: string | undefined;
  handleTimeClick?: (time: number) => void;
}

const LectureChatBot: React.FC<LectureChatBotProps> = ({ videoId, handleTimeClick }) => {
  const [messages, setMessages] = useState<ChatMessageData[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const onTimeClick = (time: number) => {
    if (handleTimeClick) {
      handleTimeClick(time);
    }
  };

  const handleSendMessage = async () => {
    const text = inputValue.trim();
    if (!text || isStreaming || !videoId) return;

    // Add user message
    const userMsg: ChatMessageData = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      citations: [],
    };
    setMessages(prev => [...prev, userMsg]);
    setInputValue('');
    setIsStreaming(true);

    // Add placeholder assistant message
    const assistantId = `assistant-${Date.now()}`;
    const assistantMsg: ChatMessageData = {
      id: assistantId,
      role: 'assistant',
      content: '',
      citations: [],
    };
    setMessages(prev => [...prev, assistantMsg]);

    // SSE streaming
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch(`${API_PREFIX}/api/videos/${videoId}/chat/stream/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          session_id: sessionId,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      if (!reader) throw new Error('No response body');

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        let currentEvent = '';
        for (const line of lines) {
          if (line.startsWith('event: ')) {
            currentEvent = line.slice(7).trim();
          } else if (line.startsWith('data: ')) {
            const dataStr = line.slice(6);
            try {
              const data = JSON.parse(dataStr);

              if (currentEvent === 'token' && data.token) {
                setMessages(prev => prev.map(msg =>
                  msg.id === assistantId
                    ? { ...msg, content: msg.content + data.token }
                    : msg
                ));
              } else if (currentEvent === 'citations' && data.citations) {
                setMessages(prev => prev.map(msg =>
                  msg.id === assistantId
                    ? { ...msg, citations: data.citations }
                    : msg
                ));
              } else if (currentEvent === 'done') {
                if (data.session_id) setSessionId(data.session_id);
                if (data.message_id) {
                  setMessages(prev => prev.map(msg =>
                    msg.id === assistantId ? { ...msg, id: data.message_id } : msg
                  ));
                }
              } else if (currentEvent === 'error') {
                setMessages(prev => prev.map(msg =>
                  msg.id === assistantId
                    ? { ...msg, content: `Error: ${data.error}` }
                    : msg
                ));
              }
            } catch {
              // Skip unparseable data lines
            }
            currentEvent = '';
          }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        console.error('Chat stream error:', err);
        setMessages(prev => prev.map(msg =>
          msg.id === assistantId
            ? { ...msg, content: `Failed to get response: ${err.message}` }
            : msg
        ));
      }
    } finally {
      setIsStreaming(false);
      abortRef.current = null;
    }
  };

  const handleStopStreaming = () => {
    abortRef.current?.abort();
    setIsStreaming(false);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full text-gray-400 text-sm">
            Ask a question about this lecture...
          </div>
        )}
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div className={`max-w-[85%] ${
              msg.role === 'user'
                ? 'bg-blue-500 text-white rounded-2xl rounded-tr-none px-4 py-3'
                : 'bg-white border border-gray-200 rounded-2xl rounded-tl-none px-4 py-3 shadow-sm'
            }`}>
              {msg.role === 'assistant' ? (
                <div className="prose prose-sm max-w-none text-gray-800">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.content || (isStreaming && messages[messages.length - 1]?.id === msg.id ? '' : '...')}
                  </ReactMarkdown>
                  {isStreaming && messages[messages.length - 1]?.id === msg.id && (
                    <span className="inline-block w-2 h-4 bg-gray-400 animate-pulse ml-0.5" />
                  )}
                </div>
              ) : (
                <span>{msg.content}</span>
              )}

              {/* Citations */}
              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-2 pt-2 border-t border-gray-100">
                  <span className="text-xs text-gray-400 block mb-1">Sources:</span>
                  <div className="flex flex-wrap gap-1">
                    {msg.citations.map((cit, i) => (
                      <CitationBadge
                        key={i}
                        citation={cit}
                        onTimeClick={onTimeClick}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="shrink-0 p-3 border-t border-gray-200 bg-white">
        <div className="flex gap-2">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Ask about the lecture..."
            className="flex-1 border border-gray-300 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSendMessage()}
            disabled={isStreaming}
          />
          {isStreaming ? (
            <Button
              danger
              onClick={handleStopStreaming}
              icon={<LoadingOutlined spin />}
            >
              Stop
            </Button>
          ) : (
            <Button
              type="primary"
              onClick={handleSendMessage}
              disabled={!inputValue.trim()}
              icon={<SendOutlined />}
            >
              Send
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};

export default LectureChatBot;
