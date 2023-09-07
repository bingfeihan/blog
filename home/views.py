from django.core.paginator import Paginator, EmptyPage
from django.http import HttpResponseNotFound
from django.shortcuts import render

# Create your views here.
from django.views import View

from home.models import ArticleCategory, Article


class IndexView(View):

    """首页广告"""
    def get(self, request):

        # 1.获取所以分类信息
        categories = ArticleCategory.objects.all()
        # 2.接收用户点击的分类id
        cat_id=request.GET.get('cat_id',1)
        # 3.判断分类id进行分类的查询
        try:
            category = ArticleCategory.objects.get(id=cat_id)
        except ArticleCategory.DoesNotExist:
            return HttpResponseNotFound('没有此分类')

        # 4.获取分页参数
        page_num = request.GET.get('page_num', 1)
        page_size = request.GET.get('page_size', 10)

        # 5.根据分类信息查询文章数据
        articles = Article.objects.filter(
            category=category
        )

        # 6.创建分页器：每页N条记录
        paginator = Paginator(articles, page_size)
        # 7.获取每页商品数据
        try:
            page_articles = paginator.page(page_num)
        except EmptyPage:
            # 如果没有分页数据，默认给用户404
            return HttpResponseNotFound('empty page')

        # 获取列表页总页数
        total_page = paginator.num_pages

        # 8.组织数据传递给模板
        context = {
            'categories':categories,
            'category':category,
            'articles': page_articles,
            'page_size': page_size,
            'total_page': total_page,
            'page_num': page_num,
        }

        return render(request, 'index.html',context=context)