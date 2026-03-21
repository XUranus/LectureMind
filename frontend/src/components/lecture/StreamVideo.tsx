import { useState, useRef, useEffect } from 'react';
import { Spin } from 'antd';
import { LoadingOutlined, VideoCameraOutlined } from '@ant-design/icons';
import MuxVideo from '@mux/mux-video-react';

interface StreamVideoProps {
  src: string;
  videoRef: React.RefObject<HTMLVideoElement | null>;
  fallbackSrc?: string;
}

const StreamVideo: React.FC<StreamVideoProps> = ({ videoRef, src, fallbackSrc }) => {
  const [hasError, setHasError] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setHasError(false);
    setLoading(true);
  }, [src]);

  if (hasError) {
    // Show fallback or processing placeholder
    if (fallbackSrc) {
      return (
        <video
          ref={videoRef}
          src={fallbackSrc}
          style={{ height: '100%', width: '100%', minHeight: 360 }}
          controls
          autoPlay
          muted
        />
      );
    }
    return (
      <div
        className="flex flex-col items-center justify-center bg-gray-900 text-gray-400"
        style={{ height: '100%', width: '100%', minHeight: 360 }}
      >
        <VideoCameraOutlined style={{ fontSize: 48, marginBottom: 16 }} />
        <p className="text-lg font-medium">Video Processing</p>
        <p className="text-sm text-gray-500 mt-1">
          HLS stream is being generated. The video will be available once processing is complete.
        </p>
      </div>
    );
  }

  return (
    <div style={{ position: 'relative', minHeight: 360, width: '100%' }}>
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-gray-900 z-10">
          <Spin indicator={<LoadingOutlined style={{ fontSize: 36 }} spin />} />
        </div>
      )}
      <MuxVideo
        style={{ height: '100%', width: '100%', minHeight: 360 }}
        src={src}
        metadata={{
          video_id: 'video-id-1456',
          video_title: 'Lecture Video',
          viewer_user_id: 'user-id-bc-789',
        }}
        controls
        autoPlay
        muted
        ref={videoRef}
        onLoadedData={() => setLoading(false)}
        onError={() => { setHasError(true); setLoading(false); }}
      />
    </div>
  );
};

export default StreamVideo;
