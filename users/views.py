import re
from random import randint

from django.contrib.auth import login, authenticate, logout
from django.db import DatabaseError
from django.http import HttpResponseBadRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect

# Create your views here.
from django.urls import reverse
from django.views import View
from django_redis import get_redis_connection

from libs.captcha.captcha import captcha
from libs.yuntongxun.sms import CCP
from users.models import User
from utils.response_code import RETCODE

import logging
logger = logging.getLogger('django')

class RegisterView(View):
    """用户注册"""

    def get(self, request):
        """
        提供注册界面
        :param request: 请求对象
        :return: 注册界面
        """
        return render(request, 'register.html')

    def post(self, request):
        # 1.接收参数
        mobile = request.POST.get('mobile')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')
        smscode = request.POST.get('sms_code')

        # 2.验证数据
        # 判断参数是否齐全
        if not all([mobile, password, password2, smscode]):
            return HttpResponseBadRequest('缺少必传参数')
        # 判断手机号是否合法
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return HttpResponseBadRequest('请输入正确的手机号码')
        # 判断密码是否是8-20个数字
        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return HttpResponseBadRequest('请输入8-20位的密码')
        # 判断两次密码是否一致
        if password != password2:
            return HttpResponseBadRequest('两次输入的密码不一致')

        # 验证短信验证码
        redis_conn = get_redis_connection('default')
        sms_code_server = redis_conn.get('sms:%s' % mobile)
        if sms_code_server is None:
            return HttpResponseBadRequest('短信验证码已过期')
        if smscode != sms_code_server.decode():
            return HttpResponseBadRequest('短信验证码错误')

        # 3.保存注册数据
        try:
            # create_user 可以用系统的方法对密码加密
            user = User.objects.create_user(username=mobile, mobile=mobile, password=password)
        except DatabaseError:
            return HttpResponseBadRequest('注册失败')

        login(request,user)

        # 4.响应注册结果
        # return HttpResponse('注册成功，重定向到首页')
        # redirect 是进行重定向
        # reverse 是可以通过namespace：name 来获取到视图所对应的路由
        # return redirect(reverse('home:index'))
        response = redirect(reverse('home:index'))
        # 设置cookie
        # 登录状态，会话结束后自动过期
        response.set_cookie('is_login', True)
        # 设置用户名有效期一个月
        response.set_cookie('username', user.username, max_age=30 * 24 * 3600)

        return response



class ImageCodeView(View):

    def get(self,request):
        '''
        1.接收前端传来的uuid
        2.判断uuid是否获取到
        3.生成图片验证码
        4.将图片内容保存到redis中 ，设置过期时间
        返回图片二进制
        :param request:
        :return:
        '''


        #获取前端传递过来的参数
        uuid=request.GET.get('uuid')
        #判断参数是否为None
        if uuid is None:
            return HttpResponseBadRequest('请求参数错误')
        # 获取验证码内容和验证码图片二进制数据
        text, image = captcha.generate_captcha()
        # 将图片验内容保存到redis中，并设置过期时间
        redis_conn = get_redis_connection('default')
        redis_conn.setex('img:%s' % uuid, 300, text)
        # 返回响应，将生成的图片以content_type为image/jpeg的形式返回给请求
        return HttpResponse(image, content_type='image/jpeg')


class SmsCodeView(View):

    def get(self,request):
        # 1.接收参数
        image_code_client = request.GET.get('image_code')
        uuid = request.GET.get('uuid')
        mobile=request.GET.get('mobile')

        # 2.校验参数
        # 2.1 参数是否齐全
        if not all([image_code_client, uuid,mobile]):
            return JsonResponse({'code': RETCODE.NECESSARYPARAMERR, 'errmsg': '缺少必传参数'})
        # 2.2 图片验证码的验证
        # 创建连接到redis的对象
        redis_conn = get_redis_connection('default')
        # 提取图形验证码
        image_code_server = redis_conn.get('img:%s' % uuid)
        if image_code_server is None:
            # 图形验证码过期或者不存在
            return JsonResponse({'code': RETCODE.IMAGECODEERR, 'errmsg': '图形验证码失效'})
        # 删除图形验证码，避免恶意测试图形验证码
        try:
            redis_conn.delete('img:%s' % uuid)
        except Exception as e:
            logger.error(e)
        # 对比图形验证码   redis的数据是bytes类型
        image_code_server = image_code_server.decode()  # bytes转字符串
        if image_code_client.lower() != image_code_server.lower():  # 转小写后比较
            return JsonResponse({'code': RETCODE.IMAGECODEERR, 'errmsg': '输入图形验证码有误'})

        # 3.生成短信验证码：生成6位数验证码
        sms_code = '%06d' % randint(0, 999999)
        # 将验证码输出在控制台，以方便调试
        logger.info(sms_code)
        # 保存短信验证码到redis中，并设置有效期
        redis_conn.setex('sms:%s' % mobile, 300, sms_code)
        # 5.发送短信验证码
        # CCP().send_template_sms(mobile, [sms_code, 5],1)

        # 6.响应结果
        return JsonResponse({'code': RETCODE.OK, 'errmsg': '发送短信成功'})



class LoginView(View):

    def get(self,request):

        return render(request,'login.html')

    def post(self, request):
        # 1.接受参数
        mobile = request.POST.get('mobile')
        password = request.POST.get('password')
        remember = request.POST.get('remember')

        # 2.校验参数
        # 判断参数是否齐全
        if not all([mobile, password]):
            return HttpResponseBadRequest('缺少必传参数')

        # 判断手机号是否正确
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return HttpResponseBadRequest('请输入正确的手机号')

        # 判断密码是否是8-20个数字
        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return HttpResponseBadRequest('密码最少8位，最长20位')

        # 3.认证登录用户
        # 认证字段已经在User模型中的USERNAME_FIELD = 'mobile'修改
        # 采用系统自带的认证方法进行认证，通过返回user，错误返回None
        user = authenticate(mobile=mobile, password=password)

        if user is None:
            return HttpResponseBadRequest('用户名或密码错误')

        # 4.实现状态保持
        login(request, user)

        # 根据next参数来进行页面的跳转，用户可能点个人中心-》登录页面-》个人中心
        # 响应登录结果
        next = request.GET.get('next')
        if next:
            response = redirect(next)
        else:
            response = redirect(reverse('home:index'))


        # 5.设置状态保持的周期
        if remember != 'on':
            # 没有记住用户：浏览器会话结束就过期
            request.session.set_expiry(0)
            # 设置cookie
            response.set_cookie('is_login', True)
            response.set_cookie('username', user.username, max_age=30 * 24 * 3600)
        else:
            # 记住用户：None表示两周后过期
            request.session.set_expiry(None)
            # 设置cookie
            response.set_cookie('is_login', True, max_age=14 * 24 * 3600)
            response.set_cookie('username', user.username, max_age=30 * 24 * 3600)
        # 7.返回响应
        return response

class LogoutView(View):

    def get(self, request):
        # 清理session
        logout(request)
        # 退出登录，重定向到登录页
        response = redirect(reverse('home:index'))
        # 退出登录时清除cookie中的登录状态
        response.delete_cookie('is_login')

        return response




class ForgetPasswordView(View):

    def get(self, request):

        return render(request, 'forget_password.html')

    def post(self, request):
        # 1.接收参数
        mobile = request.POST.get('mobile')
        password = request.POST.get('password')
        password2 = request.POST.get('password2')
        smscode = request.POST.get('sms_code')

        # 2.验证数据
        # 判断参数是否齐全
        if not all([mobile, password, password2, smscode]):
            return HttpResponseBadRequest('缺少必传参数')

        # 判断手机号是否合法
        if not re.match(r'^1[3-9]\d{9}$', mobile):
            return HttpResponseBadRequest('请输入正确的手机号码')

        # 判断密码是否是8-20个数字
        if not re.match(r'^[0-9A-Za-z]{8,20}$', password):
            return HttpResponseBadRequest('请输入8-20位的密码')

        # 判断两次密码是否一致
        if password != password2:
            return HttpResponseBadRequest('两次输入的密码不一致')

        # 验证短信验证码
        redis_conn = get_redis_connection('default')
        sms_code_server = redis_conn.get('sms:%s' % mobile)
        if sms_code_server is None:
            return HttpResponseBadRequest('短信验证码已过期')
        if smscode != sms_code_server.decode():
            return HttpResponseBadRequest('短信验证码错误')

        # 3.根据手机号查询数据
        try:
            user = User.objects.get(mobile=mobile)
        except User.DoesNotExist:
            # 3.1如果该手机号不存在，则注册个新用户
            try:
                User.objects.create_user(username=mobile, mobile=mobile, password=password)
            except Exception:
                return HttpResponseBadRequest('修改失败，请稍后再试')
        else:
            # 3.2修改用户密码
            user.set_password(password)
            user.save()

        # 4.跳转到登录页面
        response = redirect(reverse('users:login'))

        return response


from django.contrib.auth.mixins import LoginRequiredMixin
# LoginRequiredMixin 如果用户未登录的话，会镜像默认跳转
# 默认的跳转连接是：account/login/?next= xxx
class UserCenterView(LoginRequiredMixin,View):

    def get(self,request):
        # 获取用户信息
        user = request.user

        # 组织模板渲染数据
        context = {
            'username': user.username,
            'mobile': user.mobile,
            'avatar': user.avatar.url if user.avatar else None,
            'user_desc': user.user_desc
        }
        return render(request,'center.html',context=context)

    def post(self, request):
        # 1.接收数据
        user = request.user
        avatar = request.FILES.get('avatar')
        username = request.POST.get('username', user.username)
        user_desc = request.POST.get('desc', user.user_desc)

        # 2.修改数据库数据
        try:
            user.username = username
            user.user_desc = user_desc
            if avatar:
                user.avatar = avatar
            user.save()
        except Exception as e:
            logger.error(e)
            return HttpResponseBadRequest('更新失败，请稍后再试')

        # 3.更新cookie信息
        # 4.返回响应，刷新页面
        response = redirect(reverse('users:center'))
        response.set_cookie('username', user.username, max_age=30 * 24 * 3600)
        return response












