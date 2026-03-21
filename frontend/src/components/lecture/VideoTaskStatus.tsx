import React, { useState, useEffect } from 'react';
import { Tag, Tooltip, Spin, Button, message } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  LoadingOutlined,
  WarningOutlined,
  ReloadOutlined,
  DownOutlined,
  UpOutlined,
} from '@ant-design/icons';
import { API_PREFIX } from '../../config';

interface TaskItem {
  id: string;
  title: string;
  status: 'pending' | 'running' | 'done' | 'error';
  result?: string;
  previous?: string | null;
}

const parseError = (task: TaskItem) => {
  if (task.status !== 'error' || !task.result) return null;
  try {
    const r = JSON.parse(task.result);
    return { error: r.error || 'Unknown', type: r.error_type || 'Error', originalError: r.original_error };
  } catch {
    return { error: task.result, type: 'Error' };
  }
};

const statusIcon = (status: string) => {
  switch (status) {
    case 'done': return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
    case 'running': return <Spin indicator={<LoadingOutlined spin style={{ fontSize: 14 }} />} />;
    case 'error': return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />;
    default: return <ClockCircleOutlined style={{ color: '#bfbfbf' }} />;
  }
};

const VideoTaskStatus: React.FC<{ videoId: string | undefined }> = ({ videoId }) => {
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const fetchTasks = async () => {
    if (!videoId) return;
    try {
      const res = await fetch(`${API_PREFIX}/api/tasks/video/${videoId}`);
      if (res.ok) setTasks(await res.json());
    } catch (e) { console.error('Failed to fetch tasks:', e); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    fetchTasks();
    const interval = setInterval(fetchTasks, 8000);
    return () => clearInterval(interval);
  }, [videoId]);

  const handleRetry = async (taskId: string) => {
    setRetrying(taskId);
    try {
      const res = await fetch(`${API_PREFIX}/api/tasks/${taskId}/retry/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
      });
      if (res.ok) {
        message.success((await res.json()).message);
        await fetchTasks();
      } else {
        message.error((await res.json()).error || 'Retry failed');
      }
    } catch { message.error('Network error'); }
    finally { setRetrying(null); }
  };

  if (loading || tasks.length === 0) return null;

  const hasError = tasks.some(t => t.status === 'error');
  const allDone = tasks.every(t => t.status === 'done');
  const isRunning = tasks.some(t => t.status === 'running');
  const doneCount = tasks.filter(t => t.status === 'done').length;

  if (allDone) return null;

  const rootFailed = tasks.find(t => {
    if (t.status !== 'error' || !t.result) return false;
    try { return JSON.parse(t.result).error_type !== 'CascadeFailure'; }
    catch { return true; }
  });

  const headerColor = hasError ? 'border-red-300 bg-red-50' : isRunning ? 'border-blue-300 bg-blue-50' : 'border-yellow-300 bg-yellow-50';
  const headerIcon = hasError ? <WarningOutlined className="text-red-500" /> : isRunning ? <LoadingOutlined spin className="text-blue-500" /> : <ClockCircleOutlined className="text-yellow-500" />;
  const headerText = hasError ? 'Processing has errors' : isRunning ? 'Processing in progress...' : 'Processing pending';

  return (
    <div className={`mb-3 border rounded-lg ${headerColor}`}>
      {/* Clickable header — always visible */}
      <div
        className="flex items-center justify-between px-4 py-2 cursor-pointer select-none"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-2">
          {headerIcon}
          <span className="font-medium text-sm">{headerText}</span>
          <span className="text-xs text-gray-500">({doneCount}/{tasks.length} steps)</span>
        </div>
        <div className="flex items-center gap-2">
          {hasError && rootFailed && (
            <Button size="small" type="primary" danger icon={<ReloadOutlined />}
              loading={retrying === rootFailed.id}
              onClick={(e) => { e.stopPropagation(); handleRetry(rootFailed.id); }}>
              Retry
            </Button>
          )}
          {expanded ? <UpOutlined className="text-gray-400" /> : <DownOutlined className="text-gray-400" />}
        </div>
      </div>

      {/* Expandable task list */}
      {expanded && (
        <div className="px-4 pb-3 space-y-1 border-t border-gray-200 pt-2">
          {tasks.map(task => {
            const err = parseError(task);
            const isCascade = err?.type === 'CascadeFailure';
            return (
              <div key={task.id} className="flex items-center gap-2 text-sm">
                {statusIcon(task.status)}
                <span className={task.status === 'error' ? 'text-red-600 font-medium' : 'text-gray-600'}>
                  {task.title}
                </span>
                {task.status === 'error' && err && (
                  <Tooltip title={err.error}>
                    <Tag color={isCascade ? 'warning' : 'error'} className="text-xs m-0">
                      {isCascade ? 'Blocked' : err.type}
                    </Tag>
                  </Tooltip>
                )}
                {task.status === 'error' && !isCascade && task.id !== rootFailed?.id && (
                  <Button size="small" type="link" icon={<ReloadOutlined />}
                    loading={retrying === task.id} className="p-0 h-auto"
                    onClick={() => handleRetry(task.id)}>
                    Retry
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default VideoTaskStatus;
