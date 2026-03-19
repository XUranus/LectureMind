import { useState, useRef, useEffect, useCallback } from 'react';
import { Spin, List, Empty } from 'antd';
import { API_PREFIX } from '../../config';
import { TranscriptData, Sentence } from '../../model';

const formatTime = (milliseconds: number): string => {
  const totalSeconds = Math.floor(milliseconds / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
};

interface LectureTranscriptsProps {
  videoId?: string;
  handleItemClick: (time: number) => void;
  currentTime?: number; // current video time in seconds
  height?: string | number;
}

const LectureTranscripts: React.FC<LectureTranscriptsProps> = ({
  videoId,
  handleItemClick,
  currentTime = 0,
  height = '200px',
}) => {
  const [transcriptData, setTranscriptData] = useState<TranscriptData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const containerRef = useRef<HTMLDivElement>(null);
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

  // Detect user scrolling — pause auto-scroll for 3 seconds
  const handleScroll = useCallback(() => {
    userScrolling.current = true;
    if (scrollTimer.current) clearTimeout(scrollTimer.current);
    scrollTimer.current = setTimeout(() => {
      userScrolling.current = false;
    }, 3000);
  }, []);

  // Find the currently active sentence
  const currentTimeMs = currentTime * 1000;
  const sentences = transcriptData?.sentences || [];
  const activeIndex = sentences.findIndex(
    (s) => currentTimeMs >= s.begin_time && currentTimeMs < s.end_time
  );

  // Auto-scroll to active sentence
  useEffect(() => {
    if (activeRef.current && !userScrolling.current && activeIndex >= 0) {
      activeRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [activeIndex]);

  return (
    <div>
      <Spin spinning={loading}>
        <div
          ref={containerRef}
          className="transcript-list-container"
          style={{ height: '100%', overflowY: 'auto' }}
          onScroll={handleScroll}
        >
          {sentences.length === 0 && !loading ? (
            <Empty description="No transcript available" />
          ) : (
            sentences.map((sentence, idx) => {
              const isActive = idx === activeIndex;
              return (
                <div
                  key={sentence.sentence_id}
                  ref={isActive ? activeRef : undefined}
                  onClick={() => handleItemClick(sentence.begin_time / 1000)}
                  className={`flex items-start gap-3 px-4 py-2 cursor-pointer transition-colors duration-200 border-b border-gray-50 ${
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
              );
            })
          )}
        </div>
      </Spin>
    </div>
  );
};

export default LectureTranscripts;
