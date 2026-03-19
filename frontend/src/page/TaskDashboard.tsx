import React, { useEffect, useState } from 'react';
import { API_PREFIX } from '../config';
import { Card, Tag, Spin, Tooltip, Empty, Button, message, Collapse } from 'antd';
import {
  CheckCircleOutlined,
  LoadingOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined,
  WarningOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';

interface Task {
  id: string;
  video: string;
  title: string;
  description: string;
  created_at: string;
  finished_at: string | null;
  status: 'pending' | 'running' | 'done' | 'error';
  result?: string;
  previous?: string | null;
}

interface VideoTaskGroup {
  videoId: string;
  videoTitle: string;
  tasks: Task[];
}

const parseTaskError = (task: Task) => {
  if (task.status !== 'error' || !task.result) return null;
  try {
    const r = JSON.parse(task.result);
    return { error: r.error || 'Unknown error', errorType: r.error_type || 'Error', originalError: r.original_error };
  } catch {
    return { error: task.result, errorType: 'Error' };
  }
};

const statusIcon = (status: Task['status']) => {
  switch (status) {
    case 'done': return <CheckCircleOutlined style={{ color: '#52c41a' }} />;
    case 'running': return <Spin indicator={<LoadingOutlined spin style={{ fontSize: 14 }} />} />;
    case 'error': return <CloseCircleOutlined style={{ color: '#ff4d4f' }} />;
    default: return <ClockCircleOutlined style={{ color: '#bfbfbf' }} />;
  }
};

const isCascadePending = (task: Task, all: Task[]): boolean => {
  if (task.status !== 'pending' || !task.previous) return false;
  const pred = all.find(t => t.id === task.previous);
  return pred ? pred.status === 'error' || isCascadePending(pred, all) : false;
};

const TaskItem: React.FC<{
  task: Task; allTasks: Task[]; onRetry: (id: string) => void; retrying: string | null;
}> = ({ task, allTasks, onRetry, retrying }) => {
  const errInfo = parseTaskError(task);
  const isBlocked = task.status === 'error' && errInfo?.errorType === 'CascadeFailure';
  const isFailed = task.status === 'error' && !isBlocked;

  return (
    <div className={`p-3 border rounded-lg ${
      isFailed ? 'bg-red-50 border-red-200' :
      isBlocked ? 'bg-orange-50 border-orange-200' :
      task.status === 'done' ? 'bg-green-50 border-green-100' :
      task.status === 'running' ? 'bg-blue-50 border-blue-100' :
      'bg-gray-50 border-gray-200'
    }`}>
      <div className="flex justify-between items-center">
        <div className="flex items-center gap-2">
          {statusIcon(task.status)}
          <span className="font-medium text-sm">{task.title}</span>
        </div>
        <div className="flex items-center gap-2">
          {task.status === 'error' && (
            <Tooltip title={errInfo?.error}>
              <Tag color={isBlocked ? 'warning' : 'error'} className="text-xs">
                {isBlocked ? 'Blocked' : 'Failed'}
              </Tag>
            </Tooltip>
          )}
          {task.status === 'done' && <Tag color="success" className="text-xs">Done</Tag>}
          {task.status === 'running' && <Tag color="processing" className="text-xs">Running</Tag>}
          {task.status === 'pending' && (
            isCascadePending(task, allTasks)
              ? <Tooltip title="Blocked by failed predecessor"><Tag color="warning" className="text-xs">Blocked</Tag></Tooltip>
              : <Tag className="text-xs">Pending</Tag>
          )}
          {isFailed && (
            <Button size="small" type="primary" danger icon={<ReloadOutlined />}
              loading={retrying === task.id} onClick={() => onRetry(task.id)}>
              Retry
            </Button>
          )}
        </div>
      </div>
      {isFailed && errInfo && (
        <div className="mt-2 ml-5 p-2 bg-red-100 border border-red-200 rounded text-xs text-red-700">
          <span className="font-semibold">{errInfo.errorType}:</span> {errInfo.error}
        </div>
      )}
      {isBlocked && errInfo && (
        <div className="mt-2 ml-5 p-2 bg-orange-100 border border-orange-200 rounded text-xs text-orange-700">
          Blocked: {errInfo.error}
          {errInfo.originalError && <span className="block mt-1">Root cause: {errInfo.originalError}</span>}
        </div>
      )}
      <div className="text-xs text-gray-400 mt-1 ml-5">
        {dayjs(task.created_at).format('HH:mm:ss')}
        {task.finished_at && ` → ${dayjs(task.finished_at).format('HH:mm:ss')}`}
      </div>
    </div>
  );
};

const TaskDashboard: React.FC = () => {
  const [videoGroups, setVideoGroups] = useState<VideoTaskGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [retrying, setRetrying] = useState<string | null>(null);

  const loadTasks = async () => {
    try {
      const videosRes = await fetch(`${API_PREFIX}/api/videos`);
      const videos: { id: string; title: string }[] = await videosRes.json();
      const groups = await Promise.all(
        videos.map(async (video) => {
          try {
            const res = await fetch(`${API_PREFIX}/api/tasks/video/${video.id}`);
            const tasks: Task[] = await res.json();
            if (tasks?.length) return { videoId: video.id, videoTitle: video.title, tasks };
          } catch { /* skip */ }
          return null;
        })
      );
      setVideoGroups(groups.filter((g): g is VideoTaskGroup => g !== null) as VideoTaskGroup[]);
    } catch (error) {
      console.error('Error loading tasks:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleRetry = async (taskId: string) => {
    setRetrying(taskId);
    try {
      const res = await fetch(`${API_PREFIX}/api/tasks/${taskId}/retry/`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
      });
      if (res.ok) {
        const data = await res.json();
        message.success(data.message);
        await loadTasks();
      } else {
        const err = await res.json();
        message.error(err.error || 'Retry failed');
      }
    } catch { message.error('Network error'); }
    finally { setRetrying(null); }
  };

  useEffect(() => {
    loadTasks();
    const interval = setInterval(loadTasks, 10000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="flex justify-center py-16"><Spin size="large" /></div>;
  if (videoGroups.length === 0) return <Empty description="No processing tasks yet" className="py-16" />;

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h2 className="text-xl font-bold mb-4">Video Processing Tasks</h2>
      <Collapse
        defaultActiveKey={videoGroups.filter(g => g.tasks.some(t => t.status !== 'done')).map(g => g.videoId)}
        items={videoGroups.map(group => {
          const allDone = group.tasks.every(t => t.status === 'done');
          const hasError = group.tasks.some(t => t.status === 'error');
          const isRunning = group.tasks.some(t => t.status === 'running');
          const doneCount = group.tasks.filter(t => t.status === 'done').length;
          const icon = allDone ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> :
                       hasError ? <CloseCircleOutlined style={{ color: '#ff4d4f' }} /> :
                       isRunning ? <LoadingOutlined spin /> :
                       <ClockCircleOutlined style={{ color: '#bfbfbf' }} />;

          return {
            key: group.videoId,
            label: (
              <div className="flex items-center gap-2 w-full">
                {icon}
                <span className="font-medium">{group.videoTitle || group.videoId.slice(0, 8) + '...'}</span>
                <span className="text-sm text-gray-400 ml-auto mr-2">
                  {doneCount}/{group.tasks.length}
                </span>
                {hasError ? <Tag color="error" className="m-0">Failed</Tag> :
                 allDone ? <Tag color="success" className="m-0">Done</Tag> :
                 isRunning ? <Tag color="processing" className="m-0">Running</Tag> :
                 <Tag className="m-0">Pending</Tag>}
              </div>
            ),
            children: (
              <div className="space-y-2">
                {group.tasks.map(task => (
                  <TaskItem key={task.id} task={task} allTasks={group.tasks}
                    onRetry={handleRetry} retrying={retrying} />
                ))}
              </div>
            ),
          };
        })}
      />
    </div>
  );
};

export default TaskDashboard;
