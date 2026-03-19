import React, { useState, useRef, useEffect } from 'react';
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

import { ThumbnailItem } from '../model';

interface ThumbnailScrollerProps {
  thumbnails: ThumbnailItem[];
  handleThumbnailClick: (time: number) => void;
}

const ThumbnailScroller: React.FC<ThumbnailScrollerProps> = ({ thumbnails, handleThumbnailClick }) => (
  <div className="w-full overflow-x-auto pb-2 scrollbar-hide">
    <div className="flex space-x-4 min-w-max p-2">
      {thumbnails.map((item) => (
        <div
          key={item.id}
          className="relative flex-shrink-0 w-32 h-24 cursor-pointer group"
          onClick={() => handleThumbnailClick(item.timeSecond)}
        >
          <img
            src={item.imageUrl}
            alt={`Thumbnail at ${item.timeSecond}s`}
            className="w-full h-full object-cover rounded-lg border border-gray-200 shadow-sm"
          />
          <div className="absolute inset-0 bg-black bg-opacity-50 rounded-lg flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200">
            <span className="text-white font-medium text-sm">{item.timeSecond}s</span>
          </div>
        </div>
      ))}
    </div>
  </div>
);

const LectureVideoAnalysis: React.FC = () => {
  const [thumbnails, setThumbnails] = useState<ThumbnailItem[]>([]);
  const { videoId } = useParams();
  const [videoUrl, setVideoUrl] = useState('');
  const videoRef = useRef<HTMLVideoElement>(null);
  const isProcessing = false;

  const jumpVideoTime = (time: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = time;
      videoRef.current.play();
    }
  };

  const rightTabItems: TabsProps['items'] = [
    {
      key: '1',
      label: 'Transcript',
      children: (
        <div className="h-full h-[700px] overflow-auto">
          <LectureTranscripts videoId={videoId} handleItemClick={jumpVideoTime} />
        </div>
      ),
    },
    {
      key: '2',
      label: 'Sections',
      children: (
        <div className="p-4 h-full h-[700px]">
          <LectureSections handleItemClick={jumpVideoTime} videoId={videoId} />
        </div>
      ),
    },
    {
      key: '3',
      label: 'Knowledge',
      children: (
        <div className="p-4 h-full h-[700px] overflow-auto">
          <LectureKnowledge handleItemClick={jumpVideoTime} videoId={videoId} />
        </div>
      ),
    },
    {
      key: '4',
      label: 'Summary',
      children: (
        <div className="p-4 h-full h-[700px] overflow-auto">
          <LectureSummary videoId={videoId} />
        </div>
      ),
    },
    {
      key: '5',
      label: 'Mindmap',
      children: (
        <div className="h-full h-[700px]">
          <LectureMindmap videoId={videoId} />
        </div>
      ),
    },
    {
      key: '6',
      label: 'Chat',
      children: (
        <div className="h-full h-[700px]">
          <LectureChatBot videoId={videoId} handleTimeClick={jumpVideoTime} />
        </div>
      ),
    },
  ];

  useEffect(() => {
    const fetchVideoSource = async () => {
      try {
        const response = await fetch(`${API_PREFIX}/api/videos/${videoId}`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        setVideoUrl(data['video_url']);
      } catch (error) {
        console.error('Failed to fetch video source:', error);
      }
    };
    fetchVideoSource();
  }, [videoId]);

  useEffect(() => {
    const fetchSlidesThumbnails = async () => {
      const transformResponse = (apiData: any[]): ThumbnailItem[] =>
        apiData.map((item) => ({
          id: item.id,
          timeSecond: item.time_second,
          imageUrl: item.image_url,
        }));
      try {
        const response = await fetch(`${API_PREFIX}/api/videos/${videoId}/thumbnails`);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const data = await response.json();
        setThumbnails(transformResponse(data));
      } catch (error) {
        console.error('Failed to fetch slides thumbs:', error);
      }
    };
    fetchSlidesThumbnails();
  }, [videoId]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex flex-col md:flex-row gap-6 h-full">
        {/* Left Video Section */}
        <div className="md:w-1/2 overflow-hidden">
          {isProcessing ? (
            <div className="flex items-center justify-center h-full">
              <Spin
                size="large"
                tip="Processing your video..."
                indicator={<LoadingOutlined style={{ fontSize: 48 }} spin />}
              />
            </div>
          ) : (
            <div className="w-full rounded-xl object-contain">
              <StreamVideo
                videoRef={videoRef}
                src={`${API_PREFIX}/media/streams/${videoId}/master-stream.m3u8`}
              />
              <ThumbnailScroller handleThumbnailClick={jumpVideoTime} thumbnails={thumbnails} />
            </div>
          )}
        </div>

        {/* Right Section */}
        <div className="md:w-1/2 h-full flex flex-col overflow-hidden">
          <Tabs animated items={rightTabItems} className="w-full h-full" defaultActiveKey="1" />
        </div>
      </div>
    </div>
  );
};

export default LectureVideoAnalysis;
