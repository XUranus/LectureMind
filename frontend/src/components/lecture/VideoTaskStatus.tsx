import React, { useState, useEffect } from 'react';
import { Alert, Tag, Tooltip, Collapse, Spin } from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  ClockCircleOutlined,
  LoadingOutlined,
  WarningOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import { API_PREFIX } from '../../config';

interface TaskItem {
  id: string;
  title: string;
  status: 'pending' | 'running' | 'done' | 'error';
  result?: string;
  previous?: string | null;
  finished_at?: string | null;
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

interface VideoTaskStatusProps {
  videoId: string | undefined;
}

const VideoTaskStatus: React.FC<VideoTaskStatusProps> = ({ videoId }) => {
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchTasks = async () => {
    if (!videoId) return;
    try {
      const res = await fetch(`${API_PREFIX}/api/tasks/video/${videoId}`);
      if (res.ok) {
        const data = await res.json();
        setTasks(data);
      }
    } catch (e) {
      console.error('Failed to fetch tasks:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTasks();
    const interval = setInterval(fetchTasks, 8000);
    return () => clearInterval(interval);
  }, [videoId]);

  if (loading || tasks.length === 0) return null;

  const hasError = tasks.some(t => t.status === 'error');
  const allDone = tasks.every(t => t.status === 'done');
  const isRunning = tasks.some(t => t.status === 'running');
  const doneCount = tasks.filter(t => t.status === 'done').length;

  if (allDone) return null; // Don't show when everything is complete

  return (
    <div className="mb-3">
      <Alert
        type={hasError ? 'error' : isRunning ? 'info' : 'warning'}
        showIcon
        icon={hasError ? <WarningOutlined /> : isRunning ? <LoadingOutlined spin /> : <ClockCircleOutlined />}
        message={
          <div className="flex items-center justify-between">
            <span className="font-medium">
              {hasError ? 'Processing has errors' : isRunning ? 'Processing in progress...' : 'Processing pending'}
            </span>
            <span className="text-sm text-gray-500">
              {doneCount}/{tasks.length} steps complete
            </span>
          </div>
        }
        description={
          <div className="mt-2 space-y-1">
            {tasks.map(task => {
              const err = parseError(task);
              return (
                <div key={task.id} className="flex items-center gap-2 text-sm">
                  {statusIcon(task.status)}
                  <span className={task.status === 'error' ? 'text-red-600 font-medium' : 'text-gray-600'}>
                    {task.title}
                  </span>
                  {task.status === 'error' && err && (
                    <Tooltip title={err.error}>
                      <Tag color={err.type === 'CascadeFailure' ? 'warning' : 'error'} className="text-xs">
                        {err.type === 'CascadeFailure' ? 'Blocked' : err.type}
                      </Tag>
                    </Tooltip>
                  )}
                </div>
              );
            })}
          </div>
        }
      />
    </div>
  );
};

export default VideoTaskStatus;
