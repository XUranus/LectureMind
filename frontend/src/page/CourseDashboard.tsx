import React, { useState, useEffect } from 'react';
import { Card, message, Modal } from 'antd';
import { API_PREFIX } from '../config';
import CourseCreationModal from '../components/lecture/CourseCreationModal';
import { DeleteOutlined } from '@ant-design/icons';
import { Course } from '../model'

const DEFAULT_COVER = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="300" height="170" viewBox="0 0 300 170"><rect width="100%" height="100%" fill="%23f0f0f0"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="16" fill="%23999">No Cover</text></svg>`;

const CourseDashboard: React.FC = () => {
  const [courses, setCourses] = useState<Course[]>([]);

  useEffect(() => {
    const fetchCourses = async () => {
        try {
            const response = await fetch(`${API_PREFIX}/api/episodes`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data : Course[] = await response.json();
            setCourses(data);
        } catch (error) {
            console.error("Failed to fetch slides thumbs:", error);
        }
    };
    
    fetchCourses();
  }, []);

  const addCourse = (course : Course) => {
    let newCourses = eval('('+JSON.stringify(courses)+')');
    newCourses.push(course);
    setCourses(newCourses);
  }

  const deleteCourse = (id : string) => {
    let newCourses : Course[] = eval('('+JSON.stringify(courses)+')');
    newCourses = newCourses.filter(x => x.id != id)
    setCourses(newCourses);
  }

  return (
    <div className="space-y-6">
      <CourseCreationModal addCourse={addCourse}/>
      {courses.map((episode) => (
        <CourseCard
          key={episode.id}
          episode={episode}
          onDeleted={deleteCourse} />
      ))}
    </div>
  );
};

// Single Course Card Component
const CourseCard: React.FC<{ episode: Course, onDeleted: (id : string)=>void }> = ({ episode, onDeleted}) => {
  const [expanded, setExpanded] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const displayVideos = expanded ? episode.videos : episode.videos.slice(0, 20);

  const toggleExpand = () => {
    setExpanded(!expanded);
  };

  const handleDelete = () => {
    Modal.confirm({
      title: 'Are you sure?',
      content: `Delete episode "${episode.title}"? This action cannot be undone.`,
      okText: 'Yes, Delete',
      okType: 'danger',
      cancelText: 'Cancel',
      centered: true,
      onOk: async () => {
        setDeleting(true);
        try {
          const response = await fetch(`${API_PREFIX}/api/episodes/delete/${episode.id}`, {
            method: 'DELETE',
            headers: {
              'Content-Type': 'application/json',
            },
          });

          if (response.ok) {
            message.success('Episode deleted successfully');
            onDeleted(episode.id); // Notify parent to remove from list
          } else {
            const errorText = await response.text();
            console.error('Delete failed:', errorText);
            message.error('Failed to delete episode');
          }
        } catch (err) {
          console.error('Network error:', err);
          message.error('Network error. Please try again.');
        } finally {
          setDeleting(false);
        }
      },
    });
  };

  return (
    <Card
      title={<h2 className="text-xl font-semibold">{episode.title}</h2>}
      className="shadow-md rounded-lg"
      extra={
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="text-red-500 hover:text-red-700 transition-colors"
          aria-label="Delete episode"
        >
          <DeleteOutlined style={{ fontSize: '18px' }} />
        </button>
      }
    >
      <p className="text-gray-600 mb-4">{episode.description}</p>
      <p className="text-sm text-gray-500 mb-4">
        Created: {new Date(episode.created_at).toLocaleDateString()}
      </p>

      {/* Video Thumbnails */}
      <div className="overflow-x-auto pb-2 scrollbar-hide">
        <div className="flex space-x-3 min-w-max p-1">
          {displayVideos.map((video) => (
            <div
              key={video.id}
              className="flex-shrink-0 w-28 h-20 relative group cursor-pointer"
            >
              <img
                src={video.cover.length == 0 ? DEFAULT_COVER : video.cover}
                alt={video.title}
                className="w-full h-full object-cover rounded border border-gray-200"
                onClick={()=>{location.href=`/lecture/${video.id}`}}
              />
              {/* Optional: hover overlay or play icon could go here */}
            </div>
          ))}
        </div>
      </div>

      {/* Expand Button (only show if >20 videos) */}
      {episode.videos.length > 20 && (
        <button
          onClick={toggleExpand}
          className="mt-3 text-blue-600 hover:text-blue-800 text-sm font-medium"
        >
          {expanded ? 'Show less' : `Show all ${episode.videos.length} videos`}
        </button>
      )}
    </Card>
  );
};

export default CourseDashboard;