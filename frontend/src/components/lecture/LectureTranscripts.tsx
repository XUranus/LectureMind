import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { Spin, Empty } from 'antd';
import { API_PREFIX } from '../../config';
import { TranscriptData, Sentence } from '../../model';

const formatTime = (milliseconds: number): string => {
  const totalSeconds = Math.floor(milliseconds / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
};

// Memoized sentence row — only re-renders when isActive changes
const SentenceRow = React.memo<{
  sentence: Sentence;
  isActive: boolean;
  onClick: (time: number) => void;
}>(({ sentence, isActive, onClick }) => (
  <div
    onClick={() => onClick(sentence.begin_time / 1000)}
    className={`flex items-start gap-3 px-4 py-2 cursor-pointer transition-colors duration-150 border-b border-gray-50 ${
      isActive
        ? 'bg-blue-50 border-l-4 border-l-blue-500'
        : 'hover:bg-gray-50 border-l-4 border-l-transparent'
    }`}
  >
    <span
      className={`font-mono text-xs min-w-[45px] mt-0.5 ${
        isActive ? 'text-blue-600 font-semibold' : 'text-gray-400'
      }`}
    >
      {formatTime(sentence.begin_time)}
    </span>
    <span className={`flex-1 text-sm ${isActive ? 'text-blue-900 font-medium' : 'text-gray-700'}`}>
      {sentence.text}
    </span>
  </div>
));

interface LectureTranscriptsProps {
  videoId?: string;
  handleItemClick: (time: number) => void;
  currentTime?: number;
  height?: string | number;
}

const LectureTranscripts: React.FC<LectureTranscriptsProps> = ({
  videoId,
  handleItemClick,
  currentTime = 0,
}) => {
  const [transcriptData, setTranscriptData] = useState<TranscriptData | null>(null);
  const [loading, setLoading] = useState(true);
  const activeRef = useRef<HTMLDivElement>(null);
  const userScrolling = useRef(false);
  const scrollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const fetchTranscripts = async () => {
      try {
        const response = await fetch(`${API_PREFIX}/api/videos/${videoId}/transcript`);
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data: TranscriptData = await response.json();
        setTranscriptData(data);
      } catch (error) {
        console.error('Failed to fetch transcripts:', error);
      } finally {
        setLoading(false);
      }
    };
    if (videoId) fetchTranscripts();
  }, [videoId]);

  const handleScroll = useCallback(() => {
    userScrolling.current = true;
    if (scrollTimer.current) clearTimeout(scrollTimer.current);
    scrollTimer.current = setTimeout(() => { userScrolling.current = false; }, 3000);
  }, []);

  const sentences = transcriptData?.sentences || [];
  const currentTimeMs = currentTime * 1000;

  // Binary-search-like find for active index (sentences sorted by begin_time)
  const activeIndex = useMemo(() => {
    if (currentTime <= 0 || sentences.length === 0) return -1;
    for (let i = sentences.length - 1; i >= 0; i--) {
      if (currentTimeMs >= sentences[i].begin_time) return i;
    }
    return -1;
  }, [currentTimeMs, sentences]);

  // Auto-scroll to active
  useEffect(() => {
    if (activeRef.current && !userScrolling.current && activeIndex >= 0) {
      activeRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [activeIndex]);

  if (loading) return <Spin className="flex justify-center py-8" />;
  if (sentences.length === 0) return <Empty description="No transcript available" />;

  return (
    <div style={{ height: '100%', overflowY: 'auto' }} onScroll={handleScroll}>
      {sentences.map((sentence, idx) => {
        const isActive = idx === activeIndex;
        return (
          <div key={sentence.sentence_id} ref={isActive ? activeRef : undefined}>
            <SentenceRow sentence={sentence} isActive={isActive} onClick={handleItemClick} />
          </div>
        );
      })}
    </div>
  );
};

export default React.memo(LectureTranscripts);
