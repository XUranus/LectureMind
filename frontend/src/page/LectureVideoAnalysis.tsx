import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Spin, Tabs } from 'antd';
import type { TabsProps } from 'antd';
import { LoadingOutlined } from '@ant-design/icons';
import { useParams } from 'react-router-dom';
import { API_PREFIX } from '../config';

import './LectureVideoAnalysis.css';

import LectureChatBot from '../components/lecture/LectureChatbot';
import LectureTranscripts from '../components/lecture/LectureTranscripts';
import LectureSections from '../components/lecture/LectureSections';
import LectureKnowledge from '../components/lecture/LectureKnowledge';
import LectureSummary from '../components/lecture/LectureSummary';
import LectureMindmap from '../components/lecture/LectureMindmap';
import StreamVideo from '../components/lecture/StreamVideo';
import VideoTaskStatus from '../components/lecture/VideoTaskStatus';

import { ThumbnailItem } from '../model';

interface ThumbnailScrollerProps {
  thumbnails: ThumbnailItem[];
  handleThumbnailClick: (time: number) => void;
}

const ThumbnailScroller: React.FC<ThumbnailScrollerProps> = ({ thumbnails, handleThumbnailClick }) => (
  <div className="w-full overflow-x-auto pb-2 scrollbar-hide">
    <div className="flex space-x-3 min-w-max p-2">
      {thumbnails.map((item) => (
        <div
          key={item.id}
          className="relative flex-shrink-0 w-28 h-20 cursor-pointer group"
          onClick={() => handleThumbnailClick(item.timeSecond)}
        >
          <img
            src={item.imageUrl}
            alt={`Thumbnail at ${item.timeSecond}s`}
            className="w-full h-full object-cover rounded-lg border border-gray-200 shadow-sm"
          />
          <div className="absolute inset-0 bg-black bg-opacity-50 rounded-lg flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200">
            <span className="text-white font-medium text-xs">{item.timeSecond}s</span>
          </div>
        </div>
      ))}
    </div>
  </div>
);

// Tab content wrapper
const TabPane: React.FC<{ children: React.ReactNode; scroll?: boolean; pad?: boolean }> = ({
  children, scroll = true, pad = false,
}) => (
  <div
    className={`${pad ? 'p-4' : ''} ${scroll ? 'overflow-auto' : 'overflow-hidden'}`}
    style={{ height: 'calc(100vh - 220px)', minHeight: 400 }}
  >
    {children}
  </div>
);

const LectureVideoAnalysis: React.FC = () => {
  const [thumbnails, setThumbnails] = useState<ThumbnailItem[]>([]);
  const { videoId } = useParams();
  const videoRef = useRef<HTMLVideoElement>(null);

  // Current video playback time (updated every ~500ms)
  const [currentTime, setCurrentTime] = useState(0);

  const jumpVideoTime = useCallback((time: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = time;
      videoRef.current.play();
    }
  }, []);

  // Track video currentTime for bidirectional sync
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    let raf: number;
    const onTimeUpdate = () => {
      setCurrentTime(video.currentTime);
    };
    // Use timeupdate event (fires ~4x/sec)
    video.addEventListener('timeupdate', onTimeUpdate);
    // Also fires on seek
    video.addEventListener('seeked', onTimeUpdate);

    return () => {
      video.removeEventListener('timeupdate', onTimeUpdate);
      video.removeEventListener('seeked', onTimeUpdate);
    };
  }, [videoRef.current]); // re-bind when ref resolves

  const rightTabItems: TabsProps['items'] = [
    {
      key: '1',
      label: 'Transcript',
      children: (
        <TabPane>
          <LectureTranscripts
            videoId={videoId}
            handleItemClick={jumpVideoTime}
            currentTime={currentTime}
          />
        </TabPane>
      ),
    },
    {
      key: '2',
      label: 'Sections',
      children: (
        <TabPane pad>
          <LectureSections
            handleItemClick={jumpVideoTime}
            videoId={videoId}
            currentTime={currentTime}
          />
        </TabPane>
      ),
    },
    {
      key: '3',
      label: 'Knowledge',
      children: (
        <TabPane pad>
          <LectureKnowledge
            handleItemClick={jumpVideoTime}
            videoId={videoId}
            currentTime={currentTime}
          />
        </TabPane>
      ),
    },
    {
      key: '4',
      label: 'Summary',
      children: <TabPane pad><LectureSummary videoId={videoId} /></TabPane>,
    },
    {
      key: '5',
      label: 'Mindmap',
      children: <TabPane scroll={false}><LectureMindmap videoId={videoId} /></TabPane>,
    },
    {
      key: '6',
      label: 'Chat',
      children: <TabPane scroll={false}><LectureChatBot videoId={videoId} handleTimeClick={jumpVideoTime} /></TabPane>,
    },
  ];

  useEffect(() => {
    const fetchSlidesThumbnails = async () => {
      try {
        const response = await fetch(`${API_PREFIX}/api/videos/${videoId}/thumbnails`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        setThumbnails(
          data.map((item: any) => ({
            id: item.id,
            timeSecond: item.time_second,
            imageUrl: item.image_url,
          }))
        );
      } catch (error) {
        console.error('Failed to fetch thumbnails:', error);
      }
    };
    if (videoId) fetchSlidesThumbnails();
  }, [videoId]);

  return (
    <div className="flex flex-col" style={{ height: 'calc(100vh - 100px)' }}>
      {/* Task status banner */}
      <VideoTaskStatus videoId={videoId} />

      <div className="flex flex-col lg:flex-row gap-4 flex-1 min-h-0">
        {/* Left: Video + Thumbnails */}
        <div className="lg:w-1/2 flex flex-col shrink-0">
          <div className="w-full rounded-xl overflow-hidden bg-black">
            <StreamVideo
              videoRef={videoRef}
              src={`${API_PREFIX}/media/streams/${videoId}/master-stream.m3u8`}
              fallbackSrc={`${API_PREFIX}/media/videos/${videoId}.mp4`}
            />
          </div>
          <ThumbnailScroller handleThumbnailClick={jumpVideoTime} thumbnails={thumbnails} />
        </div>

        {/* Right: Tabs */}
        <div className="lg:w-1/2 flex flex-col min-h-0 overflow-hidden">
          <Tabs animated items={rightTabItems} className="w-full h-full" defaultActiveKey="1" />
        </div>
      </div>
    </div>
  );
};

export default LectureVideoAnalysis;
