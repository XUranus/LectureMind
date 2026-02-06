// src/App.tsx
import React, { useState, useRef } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';    

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
import VideoDashboard from './page/VideoDashboard'

const { Header, Sider, Content } = Layout;

const menuItems: MenuProps['items'] = [
  {
    key: 'Home',
    icon: <HomeOutlined />,
    label: 'Home',
  },
  {
    key : 'Videos',
    icon: <VideoCameraOutlined/>,
    label: 'Videos'
  },
  {
    key: 'Courses',
    icon: <BookOutlined />,
    label: 'Courses',
  },
  {
    key: 'Tasks',
    icon: <CheckSquareOutlined/>,
    label: 'Tasks',
  },
];


const menuKey2Links: Record<string, string> = {
  'Videos' : '/videos',
  'Courses' : '/courses',
  'Tasks' : '/tasks',
  'Home' : '/',
}


const MainLayout: React.FC = () => {
  const currentPath = window.location.pathname;
  const defaultSelectedKey = Object.keys(menuKey2Links).find(
    key => currentPath.startsWith(menuKey2Links[key])
  ) || 'Home';

  const [collapsed, setCollapsed] = useState(true);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([defaultSelectedKey]);

  const [isUploading, setIsUploading] = useState(false);
  const [uploadedVideo, setUploadedVideo] = useState<string | null>(null);

  const onMenuSelect: MenuProps['onSelect'] = (e) => {
    setSelectedKeys([e.key])
    if (menuKey2Links[e.key]) {
      location.href = menuKey2Links[e.key]
    }
  };


  return (
    <Layout className="min-h-screen bg-gray-50">
      {/* Top Navigation Bar */}
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
          <div className="relative">
            <span className="absolute -top-2 -right-2 flex h-4 w-4">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-4 w-4 bg-red-500"></span>
            </span>
            <Button>Notifications</Button>
          </div>
          <Button>Profile</Button>
        </div>
      </Header>

      <Layout>
        {/* Left Sidebar */}
        <Sider 
          width={200} 
          collapsed={collapsed}
          collapsible
          trigger={null}
          className="bg-white shadow-md"
        >
          <Menu
            mode="inline"
            defaultSelectedKeys={[defaultSelectedKey]}
            items={menuItems}
            className="border-r-0"
            selectedKeys={selectedKeys}
            onSelect={onMenuSelect}
          />
        </Sider>

        {/* Main Content */}
        <Content className="p-6">
          <BrowserRouter>
            <Routes>
              <Route 
                path="/"
                element={<UploadDashboard setUploadProgress={setUploadProgress}/>} />
              <Route 
                path="/courses"
                element={<CourseDashboard/>} />
              <Route 
                path="/tasks"
                element={<TaskDashboard/>} />
              <Route 
                path="/videos"
                element={<VideoDashboard/>} />
              <Route 
                path="/lecture/:videoId"
                element={<LectureVideoAnalysis/>} />
              <Route 
                path="/playground"
                element={<PlayGround videoId="113514"/>} />
              {/* You can add more routes here */}
            </Routes>
          </BrowserRouter>
        </Content>
      </Layout>
    </Layout>
  );
};

export default MainLayout;