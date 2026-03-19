import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, useNavigate, useLocation } from 'react-router-dom';

import { Layout, Menu, Button, Progress } from 'antd';
import {
  HomeOutlined,
  VideoCameraOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  BookOutlined,
  CheckSquareOutlined,
} from '@ant-design/icons';
import type { MenuProps } from 'antd';

import PlayGround from './components/PlayGround';
import LectureVideoAnalysis from './page/LectureVideoAnalysis';
import UploadDashboard from './page/UploadDashboard';
import TaskDashboard from './page/TaskDashboard';
import CourseDashboard from './page/CourseDashboard';
import CourseDetailPage from './page/CourseDetailPage';
import VideoDashboard from './page/VideoDashboard';

const { Header, Sider, Content } = Layout;

const menuItems: MenuProps['items'] = [
  { key: 'Home', icon: <HomeOutlined />, label: 'Home' },
  { key: 'Videos', icon: <VideoCameraOutlined />, label: 'Videos' },
  { key: 'Courses', icon: <BookOutlined />, label: 'Courses' },
  { key: 'Tasks', icon: <CheckSquareOutlined />, label: 'Tasks' },
];

const menuKey2Links: Record<string, string> = {
  Home: '/',
  Videos: '/videos',
  Courses: '/courses',
  Tasks: '/tasks',
};

const linkToMenuKey = (pathname: string): string => {
  if (pathname.startsWith('/videos') || pathname.startsWith('/lecture')) return 'Videos';
  if (pathname.startsWith('/courses')) return 'Courses';
  if (pathname.startsWith('/tasks')) return 'Tasks';
  return 'Home';
};

const AppShell: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(true);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isUploading] = useState(false);

  const selectedKey = linkToMenuKey(location.pathname);

  const onMenuSelect: MenuProps['onSelect'] = (e) => {
    const path = menuKey2Links[e.key];
    if (path) navigate(path);
  };

  return (
    <Layout className="min-h-screen bg-gray-50">
      <Header className="bg-white shadow-md flex items-center justify-between px-4 py-2">
        <div className="flex items-center">
          <Button
            type="text"
            icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
            onClick={() => setCollapsed(!collapsed)}
            className="text-gray-700 hover:text-blue-600"
          />
          <h1 className="ml-4 text-xl font-bold text-gray-800">PolyU Video Agent</h1>
        </div>
        <div className="flex items-center space-x-4">
          {isUploading && (
            <div className="w-40">
              <Progress percent={uploadProgress} size="small" />
            </div>
          )}
        </div>
      </Header>

      <Layout>
        <Sider width={200} collapsed={collapsed} collapsible trigger={null} className="bg-white shadow-md">
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            items={menuItems}
            className="border-r-0"
            onSelect={onMenuSelect}
          />
        </Sider>

        <Content className="p-6 overflow-auto" style={{ height: 'calc(100vh - 64px)' }}>
          <Routes>
            <Route path="/" element={<UploadDashboard setUploadProgress={setUploadProgress} />} />
            <Route path="/courses" element={<CourseDashboard />} />
            <Route path="/courses/:courseId" element={<CourseDetailPage />} />
            <Route path="/tasks" element={<TaskDashboard />} />
            <Route path="/videos" element={<VideoDashboard />} />
            <Route path="/lecture/:videoId" element={<LectureVideoAnalysis />} />
            <Route path="/playground" element={<PlayGround videoId="113514" />} />
          </Routes>
        </Content>
      </Layout>
    </Layout>
  );
};

const MainLayout: React.FC = () => (
  <BrowserRouter>
    <AppShell />
  </BrowserRouter>
);

export default MainLayout;
