import React, { useState, useEffect } from 'react';
import { Button, Input, Modal, Form, message } from 'antd';
import { SearchOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { Video } from '../model';
import { API_PREFIX } from '../config';

const DEFAULT_COVER = `data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="300" height="170" viewBox="0 0 300 170"><rect width="100%" height="100%" fill="%23f0f0f0"/><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" font-family="sans-serif" font-size="16" fill="%23999">No Cover</text></svg>`;

const VideoDashboard: React.FC = () => {
  const navigate = useNavigate();
  const [videos, setVideos] = useState<Video[]>([]);
  const [filteredVideos, setFilteredVideos] = useState<Video[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [loading, setLoading] = useState(true);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [currentVideo, setCurrentVideo] = useState<Video | null>(null);
  const [form] = Form.useForm();

  useEffect(() => { fetchVideos(); }, []);

  useEffect(() => {
    const filtered = videos.filter(video =>
      video.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      video.id.toLowerCase().includes(searchTerm.toLowerCase())
    );
    setFilteredVideos(filtered);
  }, [searchTerm, videos]);

  const fetchVideos = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_PREFIX}/api/videos`);
      if (!response.ok) throw new Error('Failed to fetch videos');
      const data: Video[] = await response.json();
      setVideos(data);
    } catch (error) {
      console.error('Error fetching videos:', error);
      message.error('Failed to load videos');
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (id: string) => {
    Modal.confirm({
      title: 'Are you sure?',
      content: 'This action cannot be undone.',
      okText: 'Yes',
      okType: 'danger',
      cancelText: 'No',
      onOk: async () => {
        try {
          const response = await fetch(`${API_PREFIX}/api/videos/delete/${id}/`, { method: 'DELETE' });
          if (!response.ok) throw new Error('Failed to delete video');
          setVideos(videos.filter(video => video.id !== id));
          message.success('Video deleted successfully');
        } catch (error) {
          console.error('Error deleting video:', error);
          message.error('Failed to delete video');
        }
      }
    });
  };

  const showEditModal = (video: Video) => {
    setCurrentVideo(video);
    form.setFieldsValue({ title: video.title });
    setEditModalVisible(true);
  };

  const handleEdit = async (values: { title: string }) => {
    if (!currentVideo) return;
    try {
      const response = await fetch(`${API_PREFIX}/api/videos/update/${currentVideo.id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: currentVideo.id, title: values.title }),
      });
      if (!response.ok) throw new Error('Failed to update video');
      setVideos(videos.map(v => v.id === currentVideo.id ? { ...v, title: values.title } : v));
      message.success('Video updated successfully');
      setEditModalVisible(false);
    } catch (error) {
      console.error('Error updating video:', error);
      message.error('Failed to update video');
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto">
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-4">Video Library</h1>
        <Input
          prefix={<SearchOutlined className="text-gray-400" />}
          placeholder="Search by ID or title..."
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          className="max-w-md"
        />
      </div>

      {loading ? (
        <div className="flex justify-center items-center h-64">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500" />
        </div>
      ) : filteredVideos.length === 0 ? (
        <div className="text-center py-12"><p className="text-gray-500">No videos found</p></div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6">
          {filteredVideos.map(video => (
            <div key={video.id} className="bg-white rounded-lg shadow-md overflow-hidden hover:shadow-lg transition-shadow duration-300">
              <div className="relative pb-[56.25%]">
                <img
                  src={video.cover_url ?? DEFAULT_COVER}
                  alt={video.title}
                  className="absolute inset-0 w-full h-full object-cover cursor-pointer"
                  onError={(e) => { (e.target as HTMLImageElement).src = DEFAULT_COVER; }}
                  onClick={() => navigate(`/lecture/${video.id}`)}
                />
              </div>
              <div className="p-4">
                <h3 className="font-semibold text-gray-800 truncate mb-2">{video.title}</h3>
                <p className="text-xs text-gray-500 mb-3">ID: {video.id}</p>
                <div className="flex justify-between">
                  <Button icon={<EditOutlined />} onClick={() => showEditModal(video)} size="small">Edit</Button>
                  <Button icon={<DeleteOutlined />} danger onClick={() => handleDelete(video.id)} size="small">Delete</Button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <Modal title="Edit Video Title" open={editModalVisible} onCancel={() => setEditModalVisible(false)} footer={null}>
        <Form form={form} layout="vertical" onFinish={handleEdit}>
          <Form.Item name="title" label="Title" rules={[{ required: true, message: 'Please enter a title' }]}>
            <Input />
          </Form.Item>
          <div className="flex justify-end gap-2">
            <Button onClick={() => setEditModalVisible(false)}>Cancel</Button>
            <Button type="primary" htmlType="submit">Save</Button>
          </div>
        </Form>
      </Modal>
    </div>
  );
};

export default VideoDashboard;
