"""学习日志表单。

表单只负责校验与样式，业务归属（owner/user）在视图层绑定。
"""

from django import forms

from .models import Comment, Entry, LearningPath, PathStep, StepResource, Topic

TEXTAREA_CLASS = "input textarea"


class TopicForm(forms.ModelForm):
    class Meta:
        model = Topic
        fields = ["text"]
        labels = {"text": "主题名称"}
        widgets = {
            "text": forms.TextInput(
                attrs={
                    "class": "input",
                    "placeholder": "例如：Django 源码阅读、线性代数、英语写作…",
                    "autofocus": True,
                }
            )
        }


class EntryForm(forms.ModelForm):
    class Meta:
        model = Entry
        fields = ["text", "completed"]
        labels = {"text": "学习记录", "completed": "标记为已完成"}
        widgets = {
            "text": forms.Textarea(
                attrs={
                    "class": TEXTAREA_CLASS,
                    "rows": 12,
                    "placeholder": "记录今天学到了什么：概念、代码、踩坑与结论…支持 Markdown",
                }
            ),
            "completed": forms.CheckboxInput(attrs={"class": "checkbox"}),
        }


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["text"]
        labels = {"text": ""}
        widgets = {
            "text": forms.Textarea(
                attrs={
                    "class": TEXTAREA_CLASS,
                    "rows": 3,
                    "placeholder": "写下你的补充或疑问…",
                }
            ),
        }


class LearningPathForm(forms.ModelForm):
    class Meta:
        model = LearningPath
        fields = ["title", "description", "estimated_hours"]
        widgets = {
            "title": forms.TextInput(
                attrs={"class": "input", "placeholder": "例如：三个月入门机器学习"}
            ),
            "description": forms.Textarea(
                attrs={"class": TEXTAREA_CLASS, "rows": 4, "placeholder": "这条路径要解决什么问题？"}
            ),
            "estimated_hours": forms.NumberInput(attrs={"class": "input", "min": 1}),
        }


class PathStepForm(forms.ModelForm):
    class Meta:
        model = PathStep
        fields = ["topic", "description", "estimated_hours"]
        widgets = {
            "topic": forms.Select(attrs={"class": "input"}),
            "description": forms.Textarea(
                attrs={"class": TEXTAREA_CLASS, "rows": 3, "placeholder": "这一步要完成什么？"}
            ),
            "estimated_hours": forms.NumberInput(attrs={"class": "input", "min": 1}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # 只能把自己创建的主题加入路径
        self.fields["topic"].queryset = Topic.objects.filter(owner=user)


class StepResourceForm(forms.ModelForm):
    class Meta:
        model = StepResource
        fields = ["title", "url", "resource_type", "notes"]
        widgets = {
            "title": forms.TextInput(attrs={"class": "input", "placeholder": "资源名称"}),
            "url": forms.URLInput(attrs={"class": "input", "placeholder": "https://"}),
            "resource_type": forms.Select(attrs={"class": "input"}),
            "notes": forms.Textarea(attrs={"class": TEXTAREA_CLASS, "rows": 3}),
        }
