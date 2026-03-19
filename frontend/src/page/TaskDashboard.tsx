import React, { useEffect, useState } from 'react';
import { API_PREFIX } from '../config';
import { Card, Collapse, Tag, Spin, Tooltip, Empty } from 'antd';
import {
  CheckCircleOutlined,
  LoadingOutlined,
  CloseCircleOutlined,
  ExclamationCircleOutlined,
  ClockCircleOutlined,
  WarningOutlined,
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

// Parse error details from task result JSON
const parseTaskError = (task: Task): { error: string; errorType: string; originalError?: string } | null => {
  if (task.status !== 'error' || !task.result) return null;
  try {
    const r = JSON.parse(task.result);
    return {
      error: r.error || 'Unknown error',
      errorType: r.error_type || 'Error',
      originalError: r.original_error,
    };
  } catch {
    return { error: task.result, errorType: 'Error' };
  }
};

const getStatusIcon = (status: Task['status']) => {
  switch (status) {
    case 'done': return <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 16 }} />;
    case 'running': return <Spin indicator={<LoadingOutlined spin style={{ fontSize: 16 }} />} />;
    case 'error': return <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 16 }} />;
    case 'pending':
    default: return <ClockCircleOutlined style={{ color: '#bfbfbf', fontSize: 16 }} />;
  }
};

const getStatusTag = (status: Task['status']) => {
  switch (status) {
    case 'done': return <Tag color="success" icon={<CheckCircleOutlined />}>Done</Tag>;
    case 'running': return <Tag color="processing" icon={<LoadingOutlined spin />}>Running</Tag>;
    case 'error': return <Tag color="error" icon={<CloseCircleOutlined />}>Failed</Tag>;
    case 'pending':
    default: return <Tag color="default" icon={<ClockCircleOutlined />}>Pending</Tag>;
  }
};

// Check if a pending task has a failed predecessor (cascade-pending)
const isCascadePending = (task: Task, allTasks: Task[]): boolean => {
  if (task.status !== 'pending' || !task.previous) return false;
  const pred = allTasks.find(t => t.id === task.previous);
  if (!pred) return false;
  return pred.status === 'error' || isCascadePending(pred, allTasks);
};

const getEffectiveStatusTag = (task: Task, allTasks: Task[]) => {
  if (task.status === 'error') {
    const errInfo = parseTaskError(task);
    const isCascade = errInfo?.errorType === 'CascadeFailure';
    return (
      <Tooltip title={isCascade ? `Blocked by: ${errInfo?.originalError || errInfo?.error}` : errInfo?.error}>
        <Tag color={isCascade ? 'warning' : 'error'} icon={isCascade ? <WarningOutlined /> : <CloseCircleOutlined />}>
          {isCascade ? 'Blocked' : 'Failed'}
        </Tag>
      </Tooltip>
    );
  }
  if (isCascadePending(task, allTasks)) {
    return (
      <Tooltip title="Waiting on a failed predecessor — will not run">
        <Tag color="warning" icon={<ExclamationCircleOutlined />}>Blocked</Tag>
      </Tooltip>
    );
  }
  return getStatusTag(task.status);
};

const TaskItem: React.FC<{ task: Task; allTasks: Task[] }> = ({ task, allTasks }) => {
  const errInfo = parseTaskError(task);
  const isBlocked = task.status === 'error' && errInfo?.errorType === 'CascadeFailure';
  const isFailed = task.status === 'error' && !isBlocked;
  const willBeBlocked = isCascadePending(task, allTasks);

  return (
    <div className={`p-3 border rounded-lg ${
      isFailed ? 'bg-red-50 border-red-200' :
      isBlocked || willBeBlocked ? 'bg-orange-50 border-orange-200' :
      task.status === 'done' ? 'bg-green-50 border-green-100' :
      task.status === 'running' ? 'bg-blue-50 border-blue-100' :
      'bg-gray-50 border-gray-200'
    }`}>
      <div className="flex justify-between items-start">
        <div className="flex items-center gap-2">
          {getStatusIcon(isFailed ? 'error' : willBeBlocked ? 'error' : task.status)}
          <h4 className="font-medium m-0">{task.title}</h4>
        </div>
        {getEffectiveStatusTag(task, allTasks)}
      </div>
      {task.description && (
        <p className="text-gray-500 text-sm mt-1 mb-0 ml-6">{task.description}</p>
      )}
      {/* Error details */}
      {isFailed && errInfo && (
        <div className="mt-2 ml-6 p-2 bg-red-100 border border-red-200 rounded text-xs text-red-700">
          <span className="font-semibold">{errInfo.errorType}:</span> {errInfo.error}
        </div>
      )}
      {isBlocked && errInfo && (
        <div className="mt-2 ml-6 p-2 bg-orange-100 border border-orange-200 rounded text-xs text-orange-700">
          <span className="font-semibold">Blocked:</span> {errInfo.error}
          {errInfo.originalError && <span className="block mt-1">Root cause: {errInfo.originalError}</span>}
        </div>
      )}
      <div className="text-xs text-gray-400 mt-2 ml-6">
        Created: {dayjs(task.created_at).format('YYYY-MM-DD HH:mm:ss')}
        {task.finished_at && ` | Finished: ${dayjs(task.finished_at).format('YYYY-MM-DD HH:mm:ss')}`}
      </div>
    </div>
  );
};

const VideoTaskCard: React.FC<{ group: VideoTaskGroup }> = ({ group }) => {
  const allDone = group.tasks.every(t => t.status === 'done');
  const hasError = group.tasks.some(t => t.status === 'error');
  const isRunning = group.tasks.some(t => t.status === 'running');
  const doneCount = group.tasks.filter(t => t.status === 'done').length;
  const totalCount = group.tasks.length;

  const icon = allDone ? (
    <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 18 }} />
  ) : hasError ? (
    <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 18 }} />
  ) : isRunning ? (
    <Spin indicator={<LoadingOutlined spin />} />
  ) : (
    <ClockCircleOutlined style={{ color: '#bfbfbf', fontSize: 18 }} />
  );

  return (
    <Card
      key={group.videoId}
      size="small"
      className={`shadow-sm ${hasError ? 'border-red-300 border-2' : ''}`}
      title={
        <div className="flex items-center gap-2">
          {icon}
          <span className="font-medium">Video: {group.videoId.slice(0, 8)}...</span>
          <span className="text-sm text-gray-400 font-normal">
            ({doneCount}/{totalCount} completed)
          </span>
        </div>
      }
      extra={
        <span className="text-sm">
          {hasError ? (
            <Tag color="error">Has Failures</Tag>
          ) : allDone ? (
            <Tag color="success">All Complete</Tag>
          ) : isRunning ? (
            <Tag color="processing">In Progress</Tag>
          ) : (
            <Tag>Pending</Tag>
          )}
        </span>
      }
    >
      <div className="space-y-2">
        {group.tasks.map(task => (
          <TaskItem key={task.id} task={task} allTasks={group.tasks} />
        ))}
      </div>
    </Card>
  );
};

const TaskDashboard: React.FC = () => {
  const [videoGroups, setVideoGroups] = useState<VideoTaskGroup[]>([]);
  const [loading, setLoading] = useState(true);

  const loadTasks = async () => {
    try {
      const videosRes = await fetch(`${API_PREFIX}/api/videos`);
      const videos: { id: string; title: string }[] = await videosRes.json();

      const groups = await Promise.all(
        videos.map(async (video) => {
          try {
            const res = await fetch(`${API_PREFIX}/api/tasks/video/${video.id}`);
            const tasks: Task[] = await res.json();
            if (tasks && tasks.length > 0) {
              return { videoId: video.id, videoTitle: video.title, tasks };
            }
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

  useEffect(() => {
    loadTasks();
    // Auto-refresh every 10 seconds
    const interval = setInterval(loadTasks, 10000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h2 className="text-xl font-bold mb-4">Video Processing Tasks</h2>
      {loading ? (
        <div className="flex justify-center py-16"><Spin size="large" /></div>
      ) : videoGroups.length === 0 ? (
        <Empty description="No processing tasks yet" />
      ) : (
        <div className="space-y-4">
          {videoGroups.map(group => (
            <VideoTaskCard key={group.videoId} group={group} />
          ))}
        </div>
      )}
    </div>
  );
};

export default TaskDashboard;
