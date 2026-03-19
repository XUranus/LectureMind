import { useState, useRef, useEffect } from 'react';
import { Button, Spin, Tag, Tooltip, Switch, Collapse } from 'antd';
import {
  SendOutlined,
  LoadingOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  BulbOutlined,
  RobotOutlined,
  SearchOutlined,
  ThunderboltOutlined,
  ToolOutlined,
} from '@ant-design/icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { API_PREFIX } from '../../config';
import { ChatMessageData, Citation, AgentToolStep } from '../../model';

const formatTime = (seconds: number): string => {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
};

// Tool name to friendly label
const toolLabels: Record<string, string> = {
  search_knowledge: 'Searching knowledge',
  get_section_details: 'Reading section',
  get_lecture_summary: 'Getting summary',
  list_sections: 'Listing sections',
  get_transcript_at_time: 'Reading transcript',
};

const toolIcons: Record<string, React.ReactNode> = {
  search_knowledge: <SearchOutlined />,
  get_section_details: <FileTextOutlined />,
  get_lecture_summary: <BulbOutlined />,
  list_sections: <FileTextOutlined />,
  get_transcript_at_time: <ClockCircleOutlined />,
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

// Agent tool step component
interface ToolStepProps {
  step: AgentToolStep;
}

const ToolStepDisplay: React.FC<ToolStepProps> = ({ step }) => {
  const label = toolLabels[step.tool] || step.tool;
  const icon = toolIcons[step.tool] || <ToolOutlined />;
  const argsStr = Object.entries(step.args || {})
    .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
    .join(', ');

  return (
    <div className="flex items-start gap-2 text-xs text-gray-500 py-1">
      <span className="shrink-0 mt-0.5">{icon}</span>
      <div className="min-w-0">
        <span className="font-medium text-gray-600">{label}</span>
        {argsStr && <span className="ml-1 text-gray-400">({argsStr})</span>}
        {step.result && (
          <Collapse
            ghost
            size="small"
            items={[{
              key: '1',
              label: <span className="text-xs text-gray-400">Show result</span>,
              children: <pre className="text-xs text-gray-500 whitespace-pre-wrap overflow-hidden max-h-32 overflow-y-auto">{step.result}</pre>,
            }]}
          />
        )}
      </div>
    </div>
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
  const [agentMode, setAgentMode] = useState(true);
  const [currentThinking, setCurrentThinking] = useState<string | null>(null);
  const [currentToolSteps, setCurrentToolSteps] = useState<AgentToolStep[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, currentThinking, currentToolSteps]);

  const onTimeClick = (time: number) => {
    if (handleTimeClick) handleTimeClick(time);
  };

  const handleSendMessage = async () => {
    const text = inputValue.trim();
    if (!text || isStreaming || !videoId) return;

    const userMsg: ChatMessageData = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
      citations: [],
    };
    setMessages(prev => [...prev, userMsg]);
    setInputValue('');
    setIsStreaming(true);
    setCurrentThinking(null);
    setCurrentToolSteps([]);

    const assistantId = `assistant-${Date.now()}`;
    const assistantMsg: ChatMessageData = {
      id: assistantId,
      role: 'assistant',
      content: '',
      citations: [],
      toolSteps: [],
    };
    setMessages(prev => [...prev, assistantMsg]);

    const controller = new AbortController();
    abortRef.current = controller;

    const endpoint = agentMode
      ? `${API_PREFIX}/api/videos/${videoId}/agent/stream/`
      : `${API_PREFIX}/api/videos/${videoId}/chat/stream/`;

    try {
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, session_id: sessionId }),
        signal: controller.signal,
      });

      if (!response.ok) throw new Error(`HTTP ${response.status}`);

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
            try {
              const data = JSON.parse(line.slice(6));

              switch (currentEvent) {
                case 'thinking':
                  setCurrentThinking(data.thought || null);
                  break;

                case 'tool_call':
                  setCurrentThinking(null);
                  setCurrentToolSteps(prev => [
                    ...prev,
                    { tool: data.tool, args: data.args },
                  ]);
                  break;

                case 'tool_result':
                  setCurrentToolSteps(prev => {
                    const updated = [...prev];
                    const last = updated.length - 1;
                    if (last >= 0 && updated[last].tool === data.tool) {
                      updated[last] = { ...updated[last], result: data.result };
                    }
                    return updated;
                  });
                  break;

                case 'token':
                  setCurrentThinking(null);
                  if (data.token) {
                    setMessages(prev => prev.map(msg =>
                      msg.id === assistantId
                        ? { ...msg, content: msg.content + data.token }
                        : msg
                    ));
                  }
                  break;

                case 'citations':
                  if (data.citations) {
                    setMessages(prev => prev.map(msg =>
                      msg.id === assistantId
                        ? { ...msg, citations: data.citations }
                        : msg
                    ));
                  }
                  break;

                case 'done':
                  if (data.tool_steps) {
                    setMessages(prev => prev.map(msg =>
                      msg.id === assistantId
                        ? { ...msg, toolSteps: data.tool_steps }
                        : msg
                    ));
                  }
                  setCurrentToolSteps([]);
                  break;

                case 'complete':
                  if (data.session_id) setSessionId(data.session_id);
                  if (data.message_id) {
                    setMessages(prev => prev.map(msg =>
                      msg.id === assistantId ? { ...msg, id: data.message_id } : msg
                    ));
                  }
                  break;

                case 'error':
                  setMessages(prev => prev.map(msg =>
                    msg.id === assistantId
                      ? { ...msg, content: `Error: ${data.error}` }
                      : msg
                  ));
                  break;
              }
            } catch {
              // skip unparseable
            }
            currentEvent = '';
          }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setMessages(prev => prev.map(msg =>
          msg.id === assistantId
            ? { ...msg, content: `Failed to get response: ${err.message}` }
            : msg
        ));
      }
    } finally {
      setIsStreaming(false);
      setCurrentThinking(null);
      setCurrentToolSteps([]);
      abortRef.current = null;
    }
  };

  const handleStopStreaming = () => {
    abortRef.current?.abort();
    setIsStreaming(false);
    setCurrentThinking(null);
    setCurrentToolSteps([]);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Mode toggle bar */}
      <div className="shrink-0 flex items-center justify-between px-4 py-2 bg-white border-b border-gray-100">
        <div className="flex items-center gap-2 text-xs text-gray-500">
          {agentMode ? (
            <>
              <RobotOutlined className="text-purple-500" />
              <span className="font-medium text-purple-600">Agent Mode</span>
              <span className="text-gray-400">Multi-step reasoning with tools</span>
            </>
          ) : (
            <>
              <ThunderboltOutlined className="text-blue-500" />
              <span className="font-medium text-blue-600">Quick Mode</span>
              <span className="text-gray-400">Direct RAG retrieval</span>
            </>
          )}
        </div>
        <Switch
          size="small"
          checked={agentMode}
          onChange={setAgentMode}
          checkedChildren={<RobotOutlined />}
          unCheckedChildren={<ThunderboltOutlined />}
          disabled={isStreaming}
        />
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 text-sm gap-2">
            <RobotOutlined className="text-3xl text-gray-300" />
            <span>Ask a question about this lecture...</span>
            {agentMode && (
              <span className="text-xs text-gray-300">Agent will search and reason step by step</span>
            )}
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
              {/* Tool steps (agent mode) */}
              {msg.role === 'assistant' && msg.toolSteps && msg.toolSteps.length > 0 && (
                <div className="mb-2 pb-2 border-b border-gray-100">
                  <div className="flex items-center gap-1 text-xs text-purple-500 mb-1">
                    <ToolOutlined />
                    <span className="font-medium">Agent used {msg.toolSteps.length} tool{msg.toolSteps.length > 1 ? 's' : ''}</span>
                  </div>
                  {msg.toolSteps.map((step, i) => (
                    <ToolStepDisplay key={i} step={step} />
                  ))}
                </div>
              )}

              {msg.role === 'assistant' ? (
                <div className="prose prose-sm max-w-none text-gray-800">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {msg.content || (isStreaming && messages[messages.length - 1]?.id === msg.id ? '' : '...')}
                  </ReactMarkdown>
                  {isStreaming && messages[messages.length - 1]?.id === msg.id && !msg.content && (
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
                      <CitationBadge key={i} citation={cit} onTimeClick={onTimeClick} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Live agent activity indicator */}
        {isStreaming && agentMode && (currentThinking || currentToolSteps.length > 0) && (
          <div className="flex justify-start">
            <div className="max-w-[85%] bg-purple-50 border border-purple-200 rounded-2xl rounded-tl-none px-4 py-3 shadow-sm">
              {currentThinking && (
                <div className="flex items-center gap-2 text-xs text-purple-600 mb-1">
                  <LoadingOutlined spin />
                  <span>{currentThinking}</span>
                </div>
              )}
              {currentToolSteps.map((step, i) => (
                <ToolStepDisplay key={i} step={step} />
              ))}
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="shrink-0 p-3 border-t border-gray-200 bg-white">
        <div className="flex gap-2">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder={agentMode ? "Ask the agent about the lecture..." : "Ask about the lecture..."}
            className="flex-1 border border-gray-300 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSendMessage()}
            disabled={isStreaming}
          />
          {isStreaming ? (
            <Button danger onClick={handleStopStreaming} icon={<LoadingOutlined spin />}>
              Stop
            </Button>
          ) : (
            <Button type="primary" onClick={handleSendMessage} disabled={!inputValue.trim()} icon={<SendOutlined />}>
              Send
            </Button>
          )}
        </div>
      </div>
    </div>
  );
};

export default LectureChatBot;
