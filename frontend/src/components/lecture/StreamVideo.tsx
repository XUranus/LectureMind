
import { useState, useRef, useEffect } from 'react';
import { Card, Spin, List } from 'antd';
import { API_PREFIX } from '../../config';
import MuxVideo from '@mux/mux-video-react';



interface StreamVideoProps {
  src: string;
  videoRef: React.RefObject<HTMLVideoElement | null>
}

const StreamVideo: React.FC<StreamVideoProps> = ({
  videoRef, src 
}) => {

  const [loading, setLoading] = useState<boolean>(true);

//   // Fetch video transcripts
//   useEffect(() => {
//     const fetchTranscripts = async () => {
//         try {
//             const response = await fetch(`${API_PREFIX}/api/videos/${videoId}/transcript`);
//             if (!response.ok) {
//                 throw new Error(`HTTP error! status: ${response.status}`);
//             }
//             const data : TranscriptData = await response.json();
//             setTranscriptData(data);
//             setLoading(false);
//         } catch (error) {
//             console.error("Failed to fetch transcripts:", error);
//         }
//     };
    
//     fetchTranscripts();
//   }, [videoId]);


  return (
    <MuxVideo
        style={{ height: '100%', width: '100%' }}
        src={src}
        metadata={{
          video_id: 'video-id-1456',
          video_title: 'Super Interesting Video',
          viewer_user_id: 'user-id-bc-789',
        }}
        controls
        autoPlay
        muted
        ref={videoRef}
      />
  );
};

export default StreamVideo;
