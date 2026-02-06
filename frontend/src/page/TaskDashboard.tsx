import React, { useEffect, useState } from 'react';
import { API_PREFIX } from '../config';
import { Card, Collapse, Tag, Spin } from 'antd';
import { CheckCircleOutlined, LoadingOutlined } from '@ant-design/icons'
import dayjs from 'dayjs';

// Define TypeScript interfaces
interface Task {
  id: string;
  video: string;
  title: string;
  description: string;
  created_at: string; // ISO string
  finished_at: string | null;
  status: 'pending' | 'running' | 'done';
}

export interface VideoTaskGroup {
  videoId: string;
  tasks: Task[];
}

interface VideoTaskPanelProps {
  videoGroups: VideoTaskGroup[];
}

interface Video {
  id : string
}

const getStatusColor = (status: Task['status']): string => {
  switch (status) {
    case 'done':
      return 'success';
    case 'running':
      return 'processing';
    case 'pending':
    default:
      return 'default';
  }
};

const VideoTaskPanel: React.FC<VideoTaskPanelProps> = ({ videoGroups }) => {
  const [activeKeys, setActiveKeys] = useState<string[]>([]);

  const handleCollapseChange = (keys: string | string[]) => {
    setActiveKeys(Array.isArray(keys) ? keys : [keys]);
  };

  return (
    <div className="w-full space-y-4">
      {videoGroups.map((group) => {
        const allDone = group.tasks.every((task) => task.status === 'done');
        const unfinishedCount = group.tasks.filter(
          (task) => task.status !== 'done'
        ).length;

        // Choose icon based on completion
        const icon = allDone ? (
          <CheckCircleOutlined style={{ color: '#52c41a', fontSize: '18px' }} />
        ) : (
          <Spin indicator={<LoadingOutlined spin />} />
        );

        return (
          <Card
            key={group.videoId}
            size="small"
            title={
              <div className="flex items-center gap-2">
                {icon}
                <span>Video: {group.videoId}</span>
              </div>
            }
            extra={
              <span className="text-sm">
                {unfinishedCount > 0
                  ? `${unfinishedCount} task(s) pending`
                  : 'All tasks completed'}
              </span>
            }
            className="shadow-sm"
          >
            <Collapse
              activeKey={activeKeys}
              onChange={handleCollapseChange}
              bordered={false}
              expandIconPlacement='start'
              
              items={[
                {
                  key: group.videoId,
                  label: unfinishedCount > 0 ? 'Show details' : 'Details',
                  children: (
                    <div className="space-y-3 mt-2">
                      {group.tasks.map((task) => (
                        <div
                          key={task.id}
                          className="p-3 border rounded-lg bg-gray-50"
                        >
                          <div className="flex justify-between items-start">
                            <h4 className="font-medium">{task.title}</h4>
                            <Tag color={getStatusColor(task.status)}>
                              {task.status}
                            </Tag>
                          </div>
                          <p className="text-gray-600 text-sm mt-1">
                            {task.description}
                          </p>
                          <div className="text-xs text-gray-500 mt-2">
                            Created: {dayjs(task.created_at).format('YYYY-MM-DD HH:mm:ss')}
                            {task.finished_at &&
                              ` | Finished: ${dayjs(task.finished_at).format('YYYY-MM-DD HH:mm:ss')}`}
                          </div>
                        </div>
                      ))}
                    </div>
                  ),
                },
              ]}
            />
          </Card>
        );
      })}
    </div>
  );
};



const TaskDashboard = () => {
  const [videoGroups, setVideoGroups] = useState<VideoTaskGroup[]>([]);

  useEffect(() => {
    // Example: fetch tasks for a specific video (or multiple videos)
    const fetchVideos = async () => {
      try {
        const response = await fetch(`${API_PREFIX}/api/videos`);
        const videos : Video[] = await response.json();
        return videos;
      } catch (error) {
        console.error('Failed to load videos:', error);
      }
    };

    const fetchTask = async (videoId : string) => {
      // Group by video (in this case, only one video, but structure supports many)
      try {
        const response = await fetch(`${API_PREFIX}/api/tasks/video/${videoId}`);
        const tasks : Task[] = await response.json();
        return tasks
      } catch (error) {
        console.error('Failed to load videos:', error);
      }
    }

  const loadTasks = async () => {
    try {
      const videos: Video[] = (await fetchVideos()) || [];
      
      // Map each video to a promise that resolves to a VideoTaskGroup (or null)
      const groupPromises = videos.map(async (video) => {
        const tasks = await fetchTask(video.id);
        if (tasks && tasks.length > 0) {
          return { videoId: video.id, tasks };
        }
        return null; // or skip later
      });

      // Wait for all fetches to complete
      const resolvedGroups = await Promise.all(groupPromises);

      // Filter out nulls (if any)
      const videoGroups = resolvedGroups.filter((group): group is VideoTaskGroup => group !== null);

      console.log('videoGroups: ', videoGroups);
      setVideoGroups(videoGroups);
    } catch (error) {
      console.error('Error loading tasks:', error);
    }
  };
    

    loadTasks();
  }, []);

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <h2 className="text-xl font-bold mb-4">Video Processing Tasks</h2>
      <VideoTaskPanel videoGroups={videoGroups} />
    </div>
  );
};

export default TaskDashboard;