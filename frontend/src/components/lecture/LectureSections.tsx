import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Spin, Tag, Empty } from 'antd';
import { ClockCircleOutlined } from '@ant-design/icons';
import { API_PREFIX } from '../../config';
import { Section } from '../../model';

const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
};

const SectionRow = React.memo<{
  section: Section;
  isActive: boolean;
  onClick: (time: number) => void;
}>(({ section, isActive, onClick }) => (
  <div
    onClick={() => onClick(section.begin_time)}
    className={`px-4 py-3 cursor-pointer transition-all duration-150 border-b border-gray-100 ${
      isActive
        ? 'bg-blue-50 border-l-4 border-l-blue-500'
        : 'hover:bg-gray-50 border-l-4 border-l-transparent'
    }`}
  >
    <div className="flex flex-col gap-1 w-full">
      <div className="flex items-center gap-2">
        <Tag color={isActive ? 'blue' : 'default'} className="m-0">
          <ClockCircleOutlined className="mr-1" />
          {formatTime(section.begin_time)} - {formatTime(section.end_time)}
        </Tag>
        <span className={`font-medium ${isActive ? 'text-blue-900' : 'text-gray-900'}`}>
          {section.title}
        </span>
      </div>
      {section.transcript_text && (
        <span className="text-gray-500 text-sm line-clamp-2">
          {section.transcript_text.substring(0, 200)}
          {section.transcript_text.length > 200 ? '...' : ''}
        </span>
      )}
    </div>
  </div>
));

interface LectureSectionsProps {
  videoId?: string;
  handleItemClick: (time: number) => void;
  currentTime?: number;
  height?: string | number;
}

const LectureSections: React.FC<LectureSectionsProps> = ({
  videoId,
  handleItemClick,
  currentTime = 0,
}) => {
  const [sections, setSections] = useState<Section[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const activeRef = useRef<HTMLDivElement>(null);
  const userScrolling = useRef(false);
  const scrollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const fetchSections = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_PREFIX}/api/videos/${videoId}/sections/`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        setSections(await response.json());
      } catch (err: any) {
        setError(err.message);
        setSections([]);
      } finally {
        setLoading(false);
      }
    };
    if (videoId) fetchSections();
  }, [videoId]);

  const handleScroll = useCallback(() => {
    userScrolling.current = true;
    if (scrollTimer.current) clearTimeout(scrollTimer.current);
    scrollTimer.current = setTimeout(() => { userScrolling.current = false; }, 3000);
  }, []);

  const sectionList = sections || [];
  const activeIndex = useMemo(() => {
    if (currentTime <= 0) return -1;
    return sectionList.findIndex(s => currentTime >= s.begin_time && currentTime < s.end_time);
  }, [currentTime, sectionList]);

  useEffect(() => {
    if (activeRef.current && !userScrolling.current && activeIndex >= 0) {
      activeRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [activeIndex]);

  if (loading) return <Spin className="flex justify-center py-8" />;
  if (error || sectionList.length === 0) {
    return <Empty description="No sections available yet. Process the video to generate sections." />;
  }

  return (
    <div style={{ height: '100%', overflowY: 'auto' }} onScroll={handleScroll}>
      {sectionList.map((section, idx) => {
        const isActive = idx === activeIndex;
        return (
          <div key={section.id} ref={isActive ? activeRef : undefined}>
            <SectionRow section={section} isActive={isActive} onClick={handleItemClick} />
          </div>
        );
      })}
    </div>
  );
};

export default React.memo(LectureSections);
