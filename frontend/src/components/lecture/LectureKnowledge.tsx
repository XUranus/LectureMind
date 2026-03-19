import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Spin, Collapse, Tag, Empty, Badge, Tooltip } from 'antd';
import {
  BulbOutlined,
  ClockCircleOutlined,
  TagsOutlined,
  StarFilled,
} from '@ant-design/icons';
import { API_PREFIX } from '../../config';
import { SectionWithKnowledge, KnowledgePoint } from '../../model';

const formatTime = (seconds: number): string => {
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
};

const importanceColor = (v: number) => v >= 0.8 ? 'red' : v >= 0.6 ? 'orange' : v >= 0.4 ? 'blue' : 'default';
const importanceLabel = (v: number) => v >= 0.8 ? 'Core' : v >= 0.6 ? 'Important' : v >= 0.4 ? 'Relevant' : 'Supplementary';

const KnowledgePointCard = React.memo<{
  kp: KnowledgePoint;
  handleTimeClick: (time: number) => void;
  isActive?: boolean;
}>(({ kp, handleTimeClick, isActive }) => (
  <div className={`border rounded-lg p-3 mb-2 transition-all duration-150 ${
    isActive ? 'bg-blue-50 border-blue-300 shadow-sm' : 'bg-white border-gray-100 hover:shadow-sm'
  }`}>
    <div className="flex items-start justify-between gap-2 mb-1">
      <div className="flex items-center gap-2 flex-1">
        <BulbOutlined className={`flex-shrink-0 mt-0.5 ${isActive ? 'text-blue-500' : 'text-yellow-500'}`} />
        <span className={`font-medium text-sm ${isActive ? 'text-blue-900' : 'text-gray-900'}`}>{kp.title}</span>
      </div>
      <Tooltip title={`Importance: ${importanceLabel(kp.importance)}`}>
        <Tag color={importanceColor(kp.importance)} className="m-0 flex-shrink-0">
          <StarFilled className="mr-1" style={{ fontSize: 10 }} />
          {importanceLabel(kp.importance)}
        </Tag>
      </Tooltip>
    </div>
    <p className="text-gray-600 text-sm mb-2 ml-6">{kp.summary}</p>
    <div className="flex flex-wrap items-center gap-1 ml-6">
      {kp.key_terms?.length > 0 && (
        <>
          <TagsOutlined className="text-gray-400 text-xs" />
          {kp.key_terms.map((term, idx) => (
            <Tag key={idx} className="m-0 text-xs" color="geekblue">{term}</Tag>
          ))}
        </>
      )}
      <span
        className={`text-xs cursor-pointer ml-auto ${isActive ? 'text-blue-500 font-medium' : 'text-gray-400 hover:text-blue-500'}`}
        onClick={() => handleTimeClick(kp.begin_time)}
      >
        <ClockCircleOutlined className="mr-1" />
        {formatTime(kp.begin_time)}
      </span>
    </div>
  </div>
));

interface LectureKnowledgeProps {
  videoId?: string;
  handleItemClick: (time: number) => void;
  currentTime?: number;
}

const LectureKnowledge: React.FC<LectureKnowledgeProps> = ({
  videoId,
  handleItemClick,
  currentTime = 0,
}) => {
  const [data, setData] = useState<SectionWithKnowledge[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const activeKpRef = useRef<HTMLDivElement>(null);
  const userScrolling = useRef(false);
  const scrollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const fetchKnowledge = async () => {
      setLoading(true);
      try {
        const response = await fetch(`${API_PREFIX}/api/videos/${videoId}/knowledge/grouped/`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        setData(await response.json());
      } catch (err: any) {
        setError(err.message);
        setData([]);
      } finally {
        setLoading(false);
      }
    };
    if (videoId) fetchKnowledge();
  }, [videoId]);

  const handleScroll = useCallback(() => {
    userScrolling.current = true;
    if (scrollTimer.current) clearTimeout(scrollTimer.current);
    scrollTimer.current = setTimeout(() => { userScrolling.current = false; }, 3000);
  }, []);

  // Find the active knowledge point
  const activeKpId = useMemo(() => {
    if (!data || currentTime <= 0) return undefined;
    for (const section of data) {
      if (currentTime >= section.begin_time && currentTime < section.end_time) {
        const kp = section.knowledge_points?.find(
          k => currentTime >= k.begin_time && currentTime < k.end_time
        );
        return kp?.id;
      }
    }
    return undefined;
  }, [data, currentTime]);

  useEffect(() => {
    if (activeKpRef.current && !userScrolling.current) {
      activeKpRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [activeKpId]);

  const totalKP = data ? data.reduce((sum, s) => sum + (s.knowledge_points?.length || 0), 0) : 0;

  if (loading) return <Spin className="flex justify-center py-8" />;
  if (error || !data || data.length === 0) {
    return <Empty description="No knowledge points available yet. Process the video to extract knowledge." />;
  }

  return (
    <div className="flex flex-col h-full" onScroll={handleScroll}>
      <div className="flex items-center gap-3 mb-3 px-1">
        <Badge count={totalKP} showZero color="blue" overflowCount={999} />
        <span className="text-gray-500 text-sm">
          knowledge points across {data.length} section{data.length !== 1 ? 's' : ''}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto">
        <Collapse
          defaultActiveKey={data.map((_, i) => String(i))}
          ghost
          items={data.map((section, idx) => {
            const isSectionActive = currentTime >= section.begin_time && currentTime < section.end_time;
            return {
              key: String(idx),
              label: (
                <div className="flex items-center gap-2">
                  <Tag color={isSectionActive ? 'blue' : 'default'} className="m-0">
                    <ClockCircleOutlined className="mr-1" />
                    {formatTime(section.begin_time)} - {formatTime(section.end_time)}
                  </Tag>
                  <span className={`font-medium ${isSectionActive ? 'text-blue-900' : 'text-gray-900'}`}>
                    {section.title || `Section ${section.order + 1}`}
                  </span>
                  <Badge count={section.knowledge_points?.length || 0} showZero color="gray" className="ml-auto" />
                </div>
              ),
              children: (
                <div className="pl-1">
                  {section.knowledge_points?.length ? (
                    section.knowledge_points.map(kp => {
                      const isKpActive = kp.id === activeKpId;
                      return (
                        <div key={kp.id} ref={isKpActive ? activeKpRef : undefined}>
                          <KnowledgePointCard kp={kp} handleTimeClick={handleItemClick} isActive={isKpActive} />
                        </div>
                      );
                    })
                  ) : (
                    <p className="text-gray-400 text-sm italic">No knowledge points for this section.</p>
                  )}
                </div>
              ),
            };
          })}
        />
      </div>
    </div>
  );
};

export default React.memo(LectureKnowledge);
