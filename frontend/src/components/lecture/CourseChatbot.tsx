import { useState, useRef, useEffect } from 'react';
import { Button, Tag, Tooltip, Collapse } from 'antd';
import {
  SendOutlined,
  LoadingOutlined,
  ClockCircleOutlined,
  FileTextOutlined,
  BulbOutlined,
  RobotOutlined,
  SearchOutlined,
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

const CitationBadge: React.FC<{ citation: Citation }> = ({ citation }) => (
  <Tooltip title={`${citation.title} (${formatTime(citation.begin_time)} - ${formatTime(citation.end_time)})`}>
    <Tag className="m-0.5" color={citation.type === 'knowledge_point' ? 'blue' : 'cyan'}>
      {citation.type === 'knowledge_point' ? <BulbOutlined className="mr-1" /> : <FileTextOutlined className="mr-1" />}
      <ClockCircleOutlined className="mr-1" />
      {formatTime(citation.begin_time)}
      <span className="ml-1 text-xs opacity-75">[Source {citation.source_num}]</span>
    </Tag>
  </Tooltip>
);

const ToolStepDisplay: React.FC<{ step: AgentToolStep }> = ({ step }) => {
  const label = toolLabels[step.tool] || step.tool;
  const icon = toolIcons[step.tool] || <ToolOutlined />;
  const argsStr = Object.entries(step.args || {}).map(([k, v]) => `${k}: ${JSON.stringify(v)}`).join(', ');
  return (
    <div className="flex items-start gap-2 text-xs text-gray-500 py-1">
      <span className="shrink-0 mt-0.5">{icon}</span>
      <div className="min-w-0">
        <span className="font-medium text-gray-600">{label}</span>
        {argsStr && <span className="ml-1 text-gray-400">({argsStr})</span>}
        {step.result && (
          <Collapse ghost size="small" items={[{
            key: '1',
            label: <span className="text-xs text-gray-400">Show result</span>,
            children: <pre className="text-xs text-gray-500 whitespace-pre-wrap overflow-hidden max-h-32 overflow-y-auto">{step.result}</pre>,
          }]} />
        )}
      </div>
    </div>
  );
};

interface CourseChatbotProps {
  courseId: string;
  courseTitle: string;
}

const CourseChatbot: React.FC<CourseChatbotProps> = ({ courseId, courseTitle }) => {
  const [messages, setMessages] = useState<ChatMessageData[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentThinking, setCurrentThinking] = useState<string | null>(null);
  const [currentToolSteps, setCurrentToolSteps] = useState<AgentToolStep[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, currentThinking, currentToolSteps]);

  const handleSendMessage = async () => {
    const text = inputValue.trim();
    if (!text || isStreaming || !courseId) return;

    const userMsg: ChatMessageData = { id: `user-${Date.now()}`, role: 'user', content: text, citations: [] };
    setMessages(prev => [...prev, userMsg]);
    setInputValue('');
    setIsStreaming(true);
    setCurrentThinking(null);
    setCurrentToolSteps([]);

    const assistantId = `assistant-${Date.now()}`;
    setMessages(prev => [...prev, { id: assistantId, role: 'assistant', content: '', citations: [], toolSteps: [] }]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch(`${API_PREFIX}/api/episodes/${courseId}/agent/stream/`, {
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
                case 'thinking': setCurrentThinking(data.thought || null); break;
                case 'tool_call':
                  setCurrentThinking(null);
                  setCurrentToolSteps(prev => [...prev, { tool: data.tool, args: data.args }]);
                  break;
                case 'tool_result':
                  setCurrentToolSteps(prev => {
                    const u = [...prev];
                    const last = u.length - 1;
                    if (last >= 0 && u[last].tool === data.tool) u[last] = { ...u[last], result: data.result };
                    return u;
                  });
                  break;
                case 'token':
                  setCurrentThinking(null);
                  if (data.token) setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, content: m.content + data.token } : m));
                  break;
                case 'citations':
                  if (data.citations) setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, citations: data.citations } : m));
                  break;
                case 'done':
                  if (data.tool_steps) setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, toolSteps: data.tool_steps } : m));
                  setCurrentToolSteps([]);
                  break;
                case 'complete':
                  if (data.session_id) setSessionId(data.session_id);
                  if (data.message_id) setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, id: data.message_id } : m));
                  break;
                case 'error':
                  setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, content: `Error: ${data.error}` } : m));
                  break;
              }
            } catch { /* skip */ }
            currentEvent = '';
          }
        }
      }
    } catch (err: any) {
      if (err.name !== 'AbortError') {
        setMessages(prev => prev.map(m => m.id === assistantId ? { ...m, content: `Failed: ${err.message}` } : m));
      }
    } finally {
      setIsStreaming(false);
      setCurrentThinking(null);
      setCurrentToolSteps([]);
      abortRef.current = null;
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="shrink-0 flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-purple-50 to-indigo-50 border-b border-purple-100">
        <RobotOutlined className="text-purple-500" />
        <span className="font-medium text-purple-700 text-sm">Course Agent</span>
        <span className="text-xs text-gray-400">Searches across all lectures in "{courseTitle}"</span>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400 text-sm gap-2">
            <RobotOutlined className="text-3xl text-gray-300" />
            <span>Ask about any topic across this course...</span>
            <span className="text-xs text-gray-300">The agent will search all lectures</span>
          </div>
        )}
        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] ${
              msg.role === 'user'
                ? 'bg-blue-500 text-white rounded-2xl rounded-tr-none px-4 py-3'
                : 'bg-white border border-gray-200 rounded-2xl rounded-tl-none px-4 py-3 shadow-sm'
            }`}>
              {msg.role === 'assistant' && msg.toolSteps && msg.toolSteps.length > 0 && (
                <div className="mb-2 pb-2 border-b border-gray-100">
                  <div className="flex items-center gap-1 text-xs text-purple-500 mb-1">
                    <ToolOutlined />
                    <span className="font-medium">Used {msg.toolSteps.length} tool{msg.toolSteps.length > 1 ? 's' : ''}</span>
                  </div>
                  {msg.toolSteps.map((step, i) => <ToolStepDisplay key={i} step={step} />)}
                </div>
              )}
              {msg.role === 'assistant' ? (
                <div className="prose prose-sm max-w-none text-gray-800">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content || '...'}</ReactMarkdown>
                </div>
              ) : <span>{msg.content}</span>}
              {msg.citations && msg.citations.length > 0 && (
                <div className="mt-2 pt-2 border-t border-gray-100">
                  <span className="text-xs text-gray-400 block mb-1">Sources:</span>
                  <div className="flex flex-wrap gap-1">
                    {msg.citations.map((cit, i) => <CitationBadge key={i} citation={cit} />)}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Live agent activity */}
        {isStreaming && (currentThinking || currentToolSteps.length > 0) && (
          <div className="flex justify-start">
            <div className="max-w-[85%] bg-purple-50 border border-purple-200 rounded-2xl rounded-tl-none px-4 py-3 shadow-sm">
              {currentThinking && (
                <div className="flex items-center gap-2 text-xs text-purple-600 mb-1">
                  <LoadingOutlined spin /><span>{currentThinking}</span>
                </div>
              )}
              {currentToolSteps.map((step, i) => <ToolStepDisplay key={i} step={step} />)}
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="shrink-0 p-3 border-t border-gray-200 bg-white">
        <div className="flex gap-2">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            placeholder="Ask about any topic across this course..."
            className="flex-1 border border-gray-300 rounded-lg px-4 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSendMessage()}
            disabled={isStreaming}
          />
          {isStreaming ? (
            <Button danger onClick={() => { abortRef.current?.abort(); setIsStreaming(false); }} icon={<LoadingOutlined spin />}>Stop</Button>
          ) : (
            <Button type="primary" onClick={handleSendMessage} disabled={!inputValue.trim()} icon={<SendOutlined />}>Send</Button>
          )}
        </div>
      </div>
    </div>
  );
};

export default CourseChatbot;
